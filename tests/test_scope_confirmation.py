"""The latest LLM interpretation must be explicitly confirmed before research."""
import asyncio
import threading

import httpx
import pytest

from app.core import db, orchestrator as pipeline


@pytest.fixture
async def api(offline):
    from app import main
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        yield client
    await main.runner.close()


def revised(brief="Compare Claude Code and Codex across IDE and cloud workflows", products=None):
    return {"subject": "AI development workflows", "domain": "AI coding tools", "research_brief": brief,
            "products": ["Claude Code", "Codex"] if products is None else products, "competitors": ["Aider"]}


async def test_initial_question_is_alone_even_without_a_category(api):
    task = (await api.post("/api/tasks", json={"query": "compare Claude Code and Codex"})).json()
    assert task["clarificationStage"] == "scope" and task["scopeRevision"] == 1
    assert [q["id"] for q in task["clarifyQuestions"]] == ["scope"]
    assert "Category to be confirmed" in task["clarifyQuestions"][0]["question"]
    detail = (await api.get(f"/api/tasks/{task['taskId']}")).json()
    assert detail["clarifyQuestions"] == task["clarifyQuestions"]
    result = await api.post(f"/api/tasks/{task['taskId']}/scope", json={"answer": "yes", "scopeRevision": 1})
    assert result.status_code == 200
    assert result.json()["clarificationStage"] == "products"
    assert [q["id"] for q in result.json()["clarifyQuestions"]] == ["products"]
    assert "scope" not in {q["id"] for q in result.json()["clarifyQuestions"]}
    assert db.get_task(task["taskId"])["status"] == "created"


async def test_multiple_corrections_use_history_and_only_latest_yes_advances(api, monkeypatch):
    task = pipeline.create_task("compare Claude Code and Codex")
    tid = task["taskId"]
    calls = []
    responses = iter([revised(), revised("Research Codex cloud only", ["Codex"])])
    def llm(messages, **kwargs):
        calls.append(messages)
        return next(responses)
    monkeypatch.setattr(pipeline, "chat_json", llm)
    for revision, answer, explanation in [(1, "roughly", "Include IDE and cloud, not just CLI"),
                                          (2, "no", "Remove Claude Code; focus on Codex cloud only")]:
        response = await api.post(f"/api/tasks/{tid}/scope", json={
            "answer": answer, "scopeRevision": revision, "explanation": explanation})
        assert response.status_code == 200
        assert response.json()["scopeRevision"] == revision + 1
        assert response.json()["clarificationStage"] == "scope"
        assert [q["id"] for q in response.json()["clarifyQuestions"]] == ["scope"]
        assert explanation in calls[-1][-1]["content"]
        restored = (await api.get(f"/api/tasks/{tid}")).json()
        assert restored["scopeRevision"] == revision + 1
        assert restored["clarificationStage"] == "scope"
    assert "Include IDE and cloud" in calls[-1][-1]["content"]
    assert (await api.post(f"/api/tasks/{tid}/scope", json={"answer": "yes", "scopeRevision": 1})).status_code == 409
    assert (await api.post(f"/api/tasks/{tid}/clarify", json={"answers": {}})).status_code == 409
    confirmed = await api.post(f"/api/tasks/{tid}/scope", json={"answer": "yes", "scopeRevision": 3})
    assert confirmed.status_code == 200 and confirmed.json()["clarificationStage"] == "products"
    assert confirmed.json()["answers"]["products"] == ["Codex"]
    assert confirmed.json()["researchBrief"] == "Research Codex cloud only"
    assert (await api.post(f"/api/tasks/{tid}/scope", json={"answer": "yes", "scopeRevision": 3})).status_code == 200
    assert len(calls) == 2
    clar = db.get_task(tid)["clarifications"]
    assert len(clar["_scope_history"]) == 2
    assert clar["_scope_confirmed_revision"] == 3


@pytest.mark.parametrize("answer", ["roughly", "no"])
async def test_correction_requires_nonempty_explanation(api, answer):
    tid = pipeline.create_task("Notion")["taskId"]
    for explanation in ("", "  "):
        result = await api.post(f"/api/tasks/{tid}/scope", json={
            "answer": answer, "scopeRevision": 1, "explanation": explanation})
        assert result.status_code == 422
    assert db.get_task(tid)["clarifications"]["_scope_revision"] == 1


async def test_failed_revision_preserves_understanding_and_can_be_retried(api, monkeypatch):
    tid = pipeline.create_task("compare Claude Code and Codex")["taskId"]
    before = db.get_task(tid)["clarifications"]
    monkeypatch.setattr(pipeline, "chat_json", lambda *a, **kw: None)
    body = {"answer": "no", "scopeRevision": 1, "explanation": "Use cloud workflows"}
    assert (await api.post(f"/api/tasks/{tid}/scope", json=body)).status_code == 503
    assert db.get_task(tid)["clarifications"] == before
    monkeypatch.setattr(pipeline, "chat_json", lambda *a, **kw: revised())
    assert (await api.post(f"/api/tasks/{tid}/scope", json=body)).status_code == 200
    assert len(db.get_task(tid)["clarifications"]["_scope_history"]) == 1


async def test_confirmation_cannot_be_bypassed_by_final_answers_stream_or_direct_pipeline(api, offline):
    tid = pipeline.create_task("Notion")["taskId"]
    response = await api.post(f"/api/tasks/{tid}/clarify", json={"answers": {
        "scope": "Yes, continue", "_scope_confirmed_revision": 1, "products": ["Notion"]}})
    assert response.status_code == 409
    assert (await api.get(f"/api/tasks/{tid}/stream")).status_code == 409
    assert db.get_task(tid)["status"] == "created"
    stream = pipeline.run_pipeline(tid)
    with pytest.raises(ValueError, match="Confirm the latest"):
        await anext(stream)
    assert not offline.searches and not offline.fetches and not db.list_reports()


async def test_concurrent_revisions_cannot_overwrite_each_other(api, monkeypatch):
    tid = pipeline.create_task("Notion")["taskId"]
    barrier = threading.Barrier(2)
    def discover(query, *, history, current_scope):
        barrier.wait(timeout=5)
        return revised(history[-1]["explanation"], ["Codex"])
    monkeypatch.setattr(pipeline, "_discover_scope", discover)
    results = await asyncio.gather(*[
        asyncio.to_thread(pipeline.submit_scope, tid, "no", 1, explanation)
        for explanation in ("Research IDE workflows", "Research cloud workflows")
    ])
    assert sorted(r.get("status_code", 200) for r in results) == [200, 409]
    clar = db.get_task(tid)["clarifications"]
    assert clar["_scope_revision"] == 2 and len(clar["_scope_history"]) == 1


async def test_confirmed_research_brief_reaches_planning_analysis_and_writing(api, offline, monkeypatch):
    original_query = "Compare Claude Code and Codex terminal tools"
    task = pipeline.create_task(original_query, "quick")
    tid = task["taskId"]
    brief = "Compare Claude Code and Codex across IDE and cloud workflows, excluding terminal-only analysis"
    monkeypatch.setattr(pipeline, "_discover_scope", lambda *a, **kw: revised(brief))
    assert pipeline.submit_scope(tid, "roughly", 1, "Include IDE and cloud workflows")["ok"]
    assert pipeline.submit_scope(tid, "yes", 2)["ok"]
    state = pipeline.task_details(db.get_task(tid))
    state = pipeline.submit_clarify(tid, {}, revision=state["clarificationRevision"])
    state = pipeline.submit_clarify(tid, {"market": "Global"}, revision=state["clarificationRevision"])
    assert pipeline.submit_clarify(tid, {}, action="start", revision=state["clarificationRevision"])["ok"]
    original = pipeline.chat_json
    prompts = []
    def record(messages, **kwargs):
        prompts.append((kwargs.get("task_kind"), "\n".join(m["content"] for m in messages)))
        return original(messages, **kwargs)
    monkeypatch.setattr(pipeline, "chat_json", record)
    events = [e async for e in pipeline.run_pipeline(tid)]
    assert any(e["type"] == "done" for e in events)
    report = db.get_report(db.list_reports()[0]["id"])
    assert report["query"] == original_query and report["research_brief"] == brief
    for kind in ("plan", "analyze", "structured", "write_section"):
        assert any(k == kind and brief in prompt for k, prompt in prompts), kind
    assert db.get_task(tid)["clarifications"]["market"] == "Global"
