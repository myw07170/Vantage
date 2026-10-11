"""End-to-end behavior with fixed public sources and independent mock role calls."""
import asyncio
import copy
import httpx
import pytest
from app import main
from app.core import db, orchestrator as pipeline
from app.core.models import ResearchScope, ReportContent, ReportItem, all_items
from app.core.review import apply_reviews
from app.core.tasks import TaskRunner, TaskUnavailable

@pytest.fixture
async def api(offline):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        yield client
    await main.runner.close()

async def completed(api, scope):
    created = await api.post("/api/tasks", json={"query": "Notion vs Obsidian"})
    assert created.status_code == 201
    tid = created.json()["task_id"]
    response = await api.post(f"/api/tasks/{tid}/start", json=scope)
    assert response.status_code == 200, response.text
    job = main.runner.jobs[tid]
    await asyncio.wait_for(job.worker, 10)
    task = db.get_task(tid)
    assert task["status"] == "done", task["error"]
    return task, db.get_report(task["report_id"])

async def test_draft_has_no_calls_and_subscribe_never_starts(api, offline):
    response = await api.post("/api/tasks", json={"query": "Notion vs Obsidian"})
    tid = response.json()["task_id"]
    assert offline.operations == [] and offline.searches == []
    response = await api.get(f"/api/tasks/{tid}/stream")
    assert response.status_code == 409
    assert db.get_task(tid)["status"] == "created"
    assert not main.runner.jobs

@pytest.mark.parametrize("url,official", [
    ("https://docs.notion.com/plans", True),
    ("https://notion.com.evil.test/plans", False),
    ("https://notion-reviews.test/plans", False),
    ("https://community.notion.com/posts/123", False),
    ("https://www.notion.com/community/posts/123", False),
])
def test_vendor_relationship_excludes_impostors_and_community(scope, url, official):
    assert pipeline.official_source(url, scope["products"][0]) is official

async def test_user_question_reaches_roles_and_review_sees_alternative_sources(api, offline, scope):
    await completed(api, scope)
    collector = [ctx for kind, ctx in offline.operations if kind == "collector"]
    analyst = [ctx for kind, ctx in offline.operations if kind == "analyst"]
    assert all(ctx["research_question"] == "Notion vs Obsidian" for ctx in collector + analyst)
    reviews = [ctx for kind, ctx in offline.operations if kind == "reviewer"]
    assert any(set(e["evidence_id"] for e in ctx["evidence"]) - {r["evidence_id"] for i in ctx["items"] for r in i["citations"]} for ctx in reviews)

@pytest.mark.parametrize("body", [{"query": " "}, {"query": "x", "mode": "quick"}, {"query": "x", "subscription_id": "legacy"}])
async def test_removed_fields_and_invalid_requests_rejected(api, body):
    assert (await api.post("/api/tasks", json=body)).status_code == 422
    assert db.list_tasks() == []

@pytest.mark.parametrize("mutation", ["five", "duplicate", "unconfirmed", "combined", "identity", "empty_topics"])
async def test_scope_rejects_ambiguous_or_invalid_products(api, scope, mutation):
    value = copy.deepcopy(scope)
    if mutation == "five":
        value["products"] *= 3
    elif mutation == "duplicate":
        value["products"][1]["name"] = "notion"
    elif mutation == "unconfirmed":
        value["products"][0]["confirmed"] = False
    elif mutation == "combined":
        value["products"][0]["name"] = "Notion + Obsidian"
    elif mutation == "identity":
        value["products"][0]["website"] = "file:///private"
    else:
        value["topics"] = []
    task = (await api.post("/api/tasks", json={"query": "test"})).json()
    response = await api.post(f'/api/tasks/{task["task_id"]}/start', json=value)
    assert response.status_code == 422
    assert not main.runner.jobs

def test_broad_scope_requires_ack_and_strategic_boundaries(scope):
    value = copy.deepcopy(scope)
    value["topics"] = [{"id": str(i), "name": "Features " + str(i), "focus": []} for i in range(7)]
    with pytest.raises(ValueError, match="Confirm the scope"):
        ResearchScope.model_validate(value)
    value["scope_acknowledged"] = True
    assert len(ResearchScope.model_validate(value).topics) == 7
    value["topics"] = [{"id": "strategy", "name": "SWOT", "focus": []}]
    with pytest.raises(ValueError, match="boundaries"):
        ResearchScope.model_validate(value)
    value["limitations"] = "Only publicly documented switching constraints for a 5-person team."
    ResearchScope.model_validate(value)

async def test_full_pipeline_persists_sources_rework_and_partial_review(api, offline, scope):
    task, report = await completed(api, scope)
    content = report["version"]["content"]
    assert content["is_mock"] and content["llm_provider"] == "mock"
    assert len(content["comparison"]) == 6
    assert content["evidence"]
    assert content["review_summary"]["rework_rounds"] == 2
    assert content["review_summary"]["counts"]["unknown"] == 6
    assert not content["charts"]
    assert content["review_summary"]["changes_message"] == "No relevant public changes found"
    assert {kind for kind, _ in offline.operations} == {"collector", "analyst", "reviewer"}
    assert all(s["model"] == "mock:mock-core" or "search" in s["model"] for s in db.get_traces_by_task(task["task_id"]))
    assert all(e["context"] and e["captured_at"] for e in content["evidence"])
    stream = await api.get(f'/api/tasks/{task["task_id"]}/stream')
    assert "event: done" in stream.text
    count = len(offline.operations)
    await api.get(f'/api/tasks/{task["task_id"]}/stream?after={task["terminal_seq"]}')
    assert len(offline.operations) == count
    assert (await api.post(f'/api/tasks/{task["task_id"]}/start', json=scope)).status_code == 409

async def test_supported_results_end_without_rework(api, scope, monkeypatch):
    original = pipeline.call_role
    def role(kind, context, max_tokens=4500):
        if kind != "reviewer":
            return original(kind, context, max_tokens)
        return {"reviews": [{"item_id": i["id"], "status": "supported", "reason": "The exact source excerpt supports this source-note statement.",
                             "evidence_ids": [r["evidence_id"] for r in i["citations"]], "quotes": i["citations"]} for i in context["items"]]}
    monkeypatch.setattr(pipeline, "call_role", role)
    task, report = await completed(api, scope)
    assert report["version"]["content"]["review_summary"]["rework_rounds"] == 0
    assert report["version"]["content"]["review_summary"]["counts"]["supported"] == 2
    assert report["version"]["content"]["review_summary"]["counts"]["unknown"] == 4

async def test_followup_fetches_new_sources_and_does_not_apply(api, offline, scope):
    _, report = await completed(api, scope)
    rid, base = report["report_id"], report["current_version_id"]
    target = report["version"]["content"]["comparison"][0]
    before = len(offline.fetches)
    response = await api.post(f"/api/reports/{rid}/followups", json={"base_version_id": base, "target_ids": [target["id"]],
                                                                  "selected_text": target["text"][:20], "question": "Check current offline limitations."})
    assert response.status_code == 202, response.text
    tid = response.json()["task_id"]
    await asyncio.wait_for(main.runner.jobs[tid].worker, 10)
    task = db.get_task(tid)
    assert task["status"] == "done", task["error"]
    candidate = db.get_version(rid, task["version_id"])
    assert candidate["state"] == "candidate" and candidate["base_version_id"] == base
    assert len(offline.fetches) > before
    assert any(kwargs.get("refresh") for _, kwargs in offline.fetches[before:])
    assert db.get_report(rid)["current_version_id"] == base
    before_items = {i["id"]: i for i in all_items(report["version"]["content"])}
    after_items = {i["id"]: i for i in all_items(candidate["content"])}
    for item_id in before_items.keys() - {target["id"]}:
        assert before_items[item_id] == after_items[item_id]
    applied = await api.post(f"/api/reports/{rid}/apply", json={"base_version_id": base, "candidate_version_id": candidate["version_id"]})
    assert applied.status_code == 201
    assert db.get_report(rid)["current_version_id"] == applied.json()["version_id"]
    assert db.get_version(rid, candidate["version_id"])["state"] == "candidate"

async def test_edits_apply_and_restore_protect_current_version(api, scope):
    _, report = await completed(api, scope)
    rid, base = report["report_id"], report["current_version_id"]
    content = report["version"]["content"]
    candidate = db.create_version(rid, content, "followup", base_version_id=base, candidate=True)
    target = content["comparison"][0]["id"]
    edited = await api.post(f"/api/reports/{rid}/edits", json={"base_version_id": base, "edits": {target: "Human correction"}})
    assert edited.status_code == 201
    current = edited.json()["version_id"]
    stale = await api.post(f"/api/reports/{rid}/edits", json={"base_version_id": base, "edits": {target: "Stale edit"}})
    assert stale.status_code == 409
    assert (await api.post(f"/api/reports/{rid}/apply", json={"base_version_id": base, "candidate_version_id": candidate["version_id"]})).status_code == 409
    assert (await api.post(f"/api/reports/{rid}/apply", json={"base_version_id": current, "candidate_version_id": candidate["version_id"]})).status_code == 409
    assert db.get_report(rid)["current_version_id"] == current
    restore = await api.post(f"/api/reports/{rid}/restore", json={"base_version_id": current, "version_id": base})
    assert restore.status_code == 201
    assert restore.json()["content"] == content
    assert restore.json()["version_id"] not in (base, current)
    assert len(db.list_versions(rid)) == 4
    assert (await api.post(f"/api/reports/{rid}/restore", json={"base_version_id": restore.json()["version_id"], "version_id": candidate["version_id"]})).status_code == 422

async def test_review_produces_candidate_not_current_overwrite(api, scope):
    _, report = await completed(api, scope)
    rid = report["report_id"]
    response = await api.post(f"/api/reports/{rid}/reviews", json={"base_version_id": report["current_version_id"]})
    assert response.status_code == 202
    tid = response.json()["task_id"]
    await main.runner.jobs[tid].worker
    assert db.get_task(tid)["status"] == "done"
    assert db.get_report(rid)["current_version_id"] == report["current_version_id"]

async def test_invalid_followup_targets_and_selection_rejected(api, scope):
    _, report = await completed(api, scope)
    rid, base = report["report_id"], report["current_version_id"]
    for target, selected in [("missing", ""), (report["version"]["content"]["comparison"][0]["id"], "not in original text")]:
        response = await api.post(f"/api/reports/{rid}/followups", json={"base_version_id": base, "target_ids": [target], "selected_text": selected, "question": "Check this"})
        assert response.status_code == 422

async def test_empty_collection_and_invalid_analysis_fail(api, scope, monkeypatch):
    monkeypatch.setattr(pipeline, "fetch_page", lambda *a, **kw: {"text": "", "blocked": True})
    task = (await api.post("/api/tasks", json={"query": "test"})).json()
    await api.post(f'/api/tasks/{task["task_id"]}/start', json=scope)
    await main.runner.jobs[task["task_id"]].worker
    assert db.get_task(task["task_id"])["status"] == "failed"
    assert db.list_reports() == []

async def test_invalid_analyst_does_not_save_fake_success(api, scope, monkeypatch):
    original = pipeline.call_role
    def role(kind, context, max_tokens=4500):
        return {"comparison": [{"text": "invalid"}]} if kind == "analyst" else original(kind, context, max_tokens)
    monkeypatch.setattr(pipeline, "call_role", role)
    task = (await api.post("/api/tasks", json={"query": "test"})).json()
    await api.post(f'/api/tasks/{task["task_id"]}/start', json=scope)
    await main.runner.jobs[task["task_id"]].worker
    assert db.get_task(task["task_id"])["status"] == "failed"
    assert db.list_reports() == []

async def test_budget_before_any_result_fails_and_retains_checkpoint(api, offline, scope):
    offline.settings.research_time_limit_seconds = 0.00001
    task = (await api.post("/api/tasks", json={"query": "test"})).json()
    await api.post(f'/api/tasks/{task["task_id"]}/start', json=scope)
    await main.runner.jobs[task["task_id"]].worker
    stored = db.get_task(task["task_id"])
    assert stored["status"] == "failed"
    assert stored["checkpoint"]
    assert db.list_reports() == []

@pytest.mark.parametrize("kind", ["followups", "reviews"])
async def test_budget_before_new_work_does_not_repackage_base_as_candidate(api, offline, scope, kind):
    _, report = await completed(api, scope)
    rid, base = report["report_id"], report["current_version_id"]
    count = len(db.list_versions(rid))
    offline.settings.research_time_limit_seconds = 0.00001
    body = {"base_version_id": base, "target_ids": [report["version"]["content"]["comparison"][0]["id"]]}
    if kind == "followups":
        body["question"] = "Check new source material"
    result = await api.post(f"/api/reports/{rid}/{kind}", json=body)
    tid = result.json()["task_id"]
    await main.runner.jobs[tid].worker
    assert db.get_task(tid)["status"] == "failed"
    assert db.get_task(tid)["checkpoint"]["content"]
    assert len(db.list_versions(rid)) == count
    assert db.get_report(rid)["current_version_id"] == base

async def test_shutdown_restart_manual_retry_preserves_original(offline, scope):
    entered = asyncio.Event()
    async def pending(tid):
        db.checkpoint(tid, {"retained": "source notes"})
        entered.set()
        await asyncio.Event().wait()
        yield {"type": "done", "data": {}}
    runner = TaskRunner(pending)
    task = db.save_task("test", payload={"scope": scope})
    runner.start(task["task_id"])
    await entered.wait()
    await runner.close()
    original = db.get_task(task["task_id"])
    assert original["status"] == "interrupted" and original["checkpoint"]["retained"]
    abandoned = db.save_task("abandoned", payload={"scope": scope})
    db.claim_task(abandoned["task_id"])
    db.interrupt_running_tasks()
    assert db.get_task(abandoned["task_id"])["status"] == "interrupted"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(f'/api/tasks/{task["task_id"]}/retry')
        assert response.status_code == 201
        retry = response.json()
        assert retry["task_id"] != task["task_id"]
        assert db.get_task(task["task_id"]) == original
        await main.runner.jobs[retry["task_id"]].worker

async def test_multiple_subscribers_share_background_job(offline, scope):
    count = 0
    entered, finish = asyncio.Event(), asyncio.Event()
    async def pipeline_fake(tid):
        nonlocal count
        count += 1
        entered.set()
        yield {"type": "progress", "data": {"percent": 20}}
        await finish.wait()
        yield {"type": "done", "data": {"report_id": "r", "version_id": "v"}}
    runner = TaskRunner(pipeline_fake)
    task = db.save_task("test", payload={"scope": scope})
    runner.start(task["task_id"])
    await entered.wait()  # Starts without an SSE connection.
    first = runner.subscribe(task["task_id"])
    assert (await anext(first))["id"] == 1
    await first.aclose()
    assert not runner.jobs[task["task_id"]].worker.done()
    second = runner.subscribe(task["task_id"], after=1)
    finish.set()
    events = [ev async for ev in second]
    assert count == 1
    assert len(events) == 1 and events[0]["type"] == "done" and events[0]["id"] == 2
    await runner.close()

async def test_cancel_before_worker_starts_releases_job(offline, scope):
    runner = TaskRunner()
    task = db.save_task("test", payload={"scope": scope})
    runner.start(task["task_id"])
    await runner.close()
    assert db.get_task(task["task_id"])["status"] == "interrupted"
    assert not runner.jobs

@pytest.mark.parametrize("route", ["experts", "experts/workload", "dashboard", "subscriptions", "evidences"])
async def test_peripheral_apis_removed(api, route):
    assert (await api.get("/api/" + route)).status_code == 404

async def test_delete_report_cascades_history_and_preserves_others(api, scope):
    _, report = await completed(api, scope)
    rid = report["report_id"]
    assert (await api.delete(f"/api/reports/{rid}")).status_code == 200
    assert db.get_report(rid) is None and db.list_versions(rid) == []
    assert db.get_traces_by_report(rid) == []
