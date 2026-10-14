"""Adaptive questions must preserve explicit answers and confirmed product scope."""
import json
import asyncio
import threading

import httpx
import pytest

from app.core import clarification as flow, db, llm, orchestrator as pipeline


@pytest.fixture
async def api(offline):
    from app import main
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        yield client
    await main.runner.close()


def question(field="purpose", *, kind="single", text="What decision should this research support?"):
    return {"status": "question", "context": {}, "question": {
        "field": field, "type": kind, "question": text,
        "options": ["Choose for myself", "Choose for a team", "Competitive research"] if kind != "text" else [],
    }}


def after_topic(query="compare Claude Code and Codex"):
    task = pipeline.create_task(query, "quick")
    return pipeline.submit_scope(task["taskId"], "yes", task["scopeRevision"])


def advance(task, answers=None, *, text="", action="answer"):
    result = pipeline.submit_clarify(task["taskId"], answers or {}, revision=task["clarificationRevision"],
                                    action=action, text=text)
    assert result["ok"], result
    return result


def after_products():
    return advance(after_topic())


def enter_followup(monkeypatch, decision=None):
    task = after_products()
    monkeypatch.setattr(pipeline, "chat_json", lambda *a, **kw: decision or question())
    return advance(task, {"market": "United States"})


async def test_fixed_steps_are_separate_and_research_requires_final_start(api):
    task = after_topic()
    tid = task["taskId"]
    assert task["clarificationStage"] == "products"
    assert [q["id"] for q in task["clarifyQuestions"]] == ["products"]
    assert (await api.get(f"/api/tasks/{tid}/stream")).status_code == 409
    task = advance(task, {"products": ["Codex"]}, text="Custom Product, Another Tool")
    assert task["answers"]["products"] == ["Codex", "Custom Product", "Another Tool"]
    assert task["clarificationStage"] == "market"
    assert [q["id"] for q in task["clarifyQuestions"]] == ["market"]
    assert "EMEA" in task["clarifyQuestions"][0]["options"]
    task = advance(task, text="English-speaking North American teams")
    assert task["answers"]["market"] == "English-speaking North American teams"
    assert task["answers"]["market_notes"] == ""
    assert task["clarificationStage"] == "ready" and task["clarifyQuestions"] == []
    assert (await api.get(f"/api/tasks/{tid}/stream")).status_code == 409
    assert not task["researchReady"] and task["canStartResearch"]
    started = advance(task, action="start")
    assert started["researchReady"] and started["status"] == "clarified"


def test_one_question_per_turn_with_option_and_custom_answers(offline, monkeypatch):
    task = after_products()
    prompts = []
    responses = iter([question(), question("focus", kind="multi", text="What matters most to your team?"),
                      {"status": "ready", "context": {"purpose": "Team selection", "audience": "Five developers",
                       "focus": ["Permissions", "Pricing"], "constraints": ["No cloud execution"]}}])
    def completion(messages, **kwargs):
        prompts.append(json.loads(messages[1]["content"]))
        return next(responses)
    monkeypatch.setattr(pipeline, "chat_json", completion)
    task = advance(task, {"market": "United States"})
    assert task["clarificationStage"] == "clarify" and len(task["clarifyQuestions"]) == 1
    qid = task["clarifyQuestions"][0]["id"]
    task = advance(task, {qid: "Choose for a team"}, text="Five developers")
    assert len(task["clarifyQuestions"]) == 1 and task["clarifyQuestions"][0]["field"] == "focus"
    qid = task["clarifyQuestions"][0]["id"]
    task = advance(task, {qid: ["Choose for myself", "Choose for a team"]}, text="Permissions and pricing; no cloud execution")
    assert task["clarificationStage"] == "ready"
    history = task["researchContext"]["answers"]
    assert history[0]["selected"] == ["Choose for a team"] and history[0]["text"] == "Five developers"
    assert len(history[1]["selected"]) == 2 and "no cloud execution" in history[1]["text"]
    assert prompts[2]["confirmedContext"]["answers"] == history
    assert task["researchContext"]["audience"] == "Five developers"


def test_detailed_request_can_finish_without_any_dynamic_question(offline, monkeypatch):
    task = after_topic("Compare Claude Code and Codex for five developers selecting a tool, focusing on permissions and pricing")
    task = advance(task)
    seen = []
    def completion(messages, **kwargs):
        seen.append(messages[1]["content"])
        return {"status": "ready", "context": {"purpose": "Tool selection", "audience": "Five developers",
                                                 "focus": ["Permissions", "Pricing"]}}
    monkeypatch.setattr(pipeline, "chat_json", completion)
    task = advance(task, {"market": "United States"})
    assert task["clarificationStage"] == "ready" and not task["clarifyQuestions"]
    assert "five developers" in seen[0]


@pytest.mark.parametrize("kind", ["single", "multi", "text"])
def test_text_only_answers_work_for_every_question_type(offline, monkeypatch, kind):
    task = enter_followup(monkeypatch, question(kind=kind))
    monkeypatch.setattr(pipeline, "chat_json", lambda *a, **kw: {"status": "ready", "context": {}})
    task = advance(task, text="My own decision and requirements")
    assert task["researchContext"]["answers"][0]["text"] == "My own decision and requirements"
    assert task["researchContext"]["answers"][0]["selected"] == []


def test_failure_saves_answer_restores_draft_and_retry_does_not_duplicate_history(offline, monkeypatch):
    task = enter_followup(monkeypatch)
    q = task["clarifyQuestions"][0]
    monkeypatch.setattr(pipeline, "chat_json", lambda *a, **kw: None)
    task = advance(task, {q["id"]: "Choose for a team"}, text="A five-person team")
    assert task["clarificationError"] and task["clarificationStage"] == "clarify"
    assert task["questionDraft"] == {"selected": ["Choose for a team"], "text": "A five-person team"}
    restored = pipeline.task_details(db.get_task(task["taskId"]))
    assert restored["questionDraft"] == task["questionDraft"]
    assert restored["clarifyQuestions"] == [q] and len(restored["researchContext"]["answers"]) == 1
    monkeypatch.setattr(pipeline, "chat_json", lambda *a, **kw: {"status": "ready", "context": {}})
    task = advance(restored, action="retry")
    assert task["clarificationStage"] == "ready" and not task["clarificationError"]
    assert len(task["researchContext"]["answers"]) == 1


def test_initial_generation_failure_still_allows_starting_with_confirmed_information(offline, monkeypatch):
    task = after_products()
    monkeypatch.setattr(pipeline, "chat_json", lambda *a, **kw: None)
    task = advance(task, {"market": "Global"}, text="European customers")
    assert task["clarificationError"] and task["clarifyQuestions"] == []
    task = advance(task, action="start")
    assert task["researchReady"]
    assert task["researchContext"]["market_notes"] == "European customers"


def test_answered_fields_are_not_repeated_under_different_wording(offline, monkeypatch):
    task = enter_followup(monkeypatch)
    qid = task["clarifyQuestions"][0]["id"]
    monkeypatch.setattr(pipeline, "chat_json", lambda *a, **kw: question(text="What will you use this research for?"))
    task = advance(task, {qid: "Choose for myself"})
    assert task["clarificationStage"] == "ready"


@pytest.mark.parametrize("action", ["answer", "start"])
def test_product_change_returns_to_confirmation_without_silently_changing_products(offline, monkeypatch, action):
    task = enter_followup(monkeypatch)
    monkeypatch.setattr(pipeline, "chat_json", lambda *a, **kw: {
        "status": "products", "context": {}, "productSuggestions": ["Cursor"]})
    task = advance(task, text="Compare Cursor instead", action=action)
    assert task["clarificationStage"] == "products" and not task["researchReady"]
    assert task["answers"]["products"] == ["Claude Code", "Codex"]
    assert "Cursor" in task["clarifyQuestions"][0]["options"]
    # A reviewed change request cannot keep looping back to products.
    task = advance(task, {"products": ["Codex", "Cursor"]})
    assert task["answers"]["products"] == ["Codex", "Cursor"]
    assert task["clarificationStage"] == "ready"


def test_start_keeps_unsubmitted_dynamic_text_and_bypasses_optional_future_questions(offline, monkeypatch):
    task = enter_followup(monkeypatch)
    calls = []
    def completion(messages, **kwargs):
        calls.append(messages)
        return question("audience", text="Which team?")
    monkeypatch.setattr(pipeline, "chat_json", completion)
    task = advance(task, text="Select tools for five developers", action="start")
    assert task["researchReady"] and task["clarifyQuestions"] == []
    assert task["researchContext"]["answers"][0]["text"] == "Select tools for five developers"
    assert len(calls) == 1


async def test_empty_unknown_or_stale_answers_cannot_advance(api, monkeypatch):
    task = enter_followup(monkeypatch)
    path = f"/api/tasks/{task['taskId']}/clarify"
    rev = task["clarificationRevision"]
    qid = task["clarifyQuestions"][0]["id"]
    for answers in ({}, {qid: "Invented option"}, {qid: ["Choose for myself", "Choose for a team"]}):
        response = await api.post(path, json={"action": "answer", "answers": answers, "clarificationRevision": rev})
        assert response.status_code == 422
    assert (await api.post(path, json={"action": "answer", "text": "An answer", "clarificationRevision": rev - 1})).status_code == 409
    assert pipeline.task_details(db.get_task(task["taskId"]))["clarificationRevision"] == rev


async def test_concurrent_answers_cannot_overwrite_a_newer_round(api, monkeypatch):
    task = enter_followup(monkeypatch)
    barrier = threading.Barrier(2)
    def generate(*args, **kwargs):
        barrier.wait(timeout=5)
        return {"status": "ready", "context": {}}
    monkeypatch.setattr(flow, "generate", generate)
    qid = task["clarifyQuestions"][0]["id"]
    results = await asyncio.gather(*[
        asyncio.to_thread(pipeline.submit_clarify, task["taskId"], {qid: choice},
                          revision=task["clarificationRevision"])
        for choice in ("Choose for myself", "Choose for a team")
    ])
    assert sorted(result.get("status_code", 200) for result in results) == [200, 409]
    restored = pipeline.task_details(db.get_task(task["taskId"]))
    assert len(restored["researchContext"]["answers"]) == 1


def test_scope_confirmation_cannot_ignore_unsubmitted_corrections(offline):
    task = pipeline.create_task("Notion")
    result = pipeline.submit_scope(task["taskId"], "yes", 1, "Actually research Obsidian")
    assert not result["ok"] and result["status_code"] == 422
    assert not pipeline.scope_is_confirmed(db.get_task(task["taskId"])["clarifications"])


async def test_existing_two_stage_tasks_keep_preferences_and_reconfirm_products(api):
    old = {"products": ["Codex"], "market": "Global", "user": "Enterprise",
           "focus": ["Permissions"], "_scope": {"products": ["Codex"], "competitors": []},
           "_scope_revision": 1, "_scope_confirmed_revision": 1, "_resolved_brief": "Research Codex"}
    db.save_task("t_old", "Research Codex", old)
    result = (await api.get("/api/tasks/t_old")).json()
    assert result["clarificationStage"] == "products"
    assert result["answers"]["market"] == "Global" and result["answers"]["user"] == "Enterprise"
    assert result["researchContext"]["previous_preferences"]["focus"] == ["Permissions"]
    assert (await api.get("/api/tasks/t_old/stream")).status_code == 409


async def test_context_reaches_search_analysis_writing_review_and_recency_filters(api, offline, monkeypatch):
    task = after_products()
    original_completion = pipeline.chat_json
    monkeypatch.setattr(pipeline, "chat_json", lambda *a, **kw: {"status": "ready", "context": {
        "purpose": "Select a tool for a regulated team", "audience": "Five enterprise developers",
        "perspective": "Buyer / end user", "focus": ["Permissions", "Pricing"],
        "constraints": ["No cloud execution"], "freshness": "month",
    }})
    task = advance(task, {"market": "United States"}, text="USD pricing")
    task = advance(task, action="start")
    monkeypatch.setattr(pipeline, "chat_json", original_completion)
    prompts, freshness = [], []
    original_json = llm.chat_json
    def record(messages, **kwargs):
        prompts.append((kwargs.get("task_kind"), "\n".join(m["content"] for m in messages)))
        return original_json(messages, **kwargs)
    monkeypatch.setattr(pipeline, "chat_json", record)
    monkeypatch.setattr(llm, "chat_json", record)
    original_search = pipeline.multi_search
    def search(queries, **kwargs):
        freshness.append(kwargs.get("freshness"))
        return original_search(queries, **kwargs)
    monkeypatch.setattr(pipeline, "multi_search", search)
    events = [e async for e in pipeline.run_pipeline(task["taskId"])]
    assert any(e["type"] == "done" for e in events)
    for kind in ("plan", "analyze", "structured", "write_section", "quality_review", "report_review"):
        assert any(k == kind and "Five enterprise developers" in p and "No cloud execution" in p for k, p in prompts), kind
    assert set(freshness) == {"month"}
    assert pipeline.MODE_CONFIG["quick"]["freshness"] == "year"
    report = db.get_report(db.list_reports()[0]["id"])
    assert report["research_context"]["purpose"] == "Select a tool for a regulated team"
    assert any(s["id"] == "persp_user" for s in report["sections"])
