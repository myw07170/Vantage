"""Task ownership and API contracts: reconnects must never rerun research."""
import asyncio

import httpx
import pytest

from app.core import db, orchestrator as pipeline
from app.core.tasks import TaskRunner, TaskUnavailable


@pytest.fixture
async def api(offline):
    from app import main
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        yield client
    await main.runner.close()


async def test_invalid_requests_do_not_create_tasks(api):
    for body in ({"query": "   "}, {"query": "Notion", "mode": "invalid"},
                 {"query": "Notion", "subscription_id": "missing"}):
        result = await api.post("/api/tasks", json=body)
        assert result.status_code in (422, 404)
    assert db._connect().execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
    for path in ("/api/tasks/missing", "/api/tasks/missing/stream", "/api/reports/missing"):
        assert (await api.get(path)).status_code == 404
    assert (await api.post("/api/tasks/missing/clarify", json={"answers": {}})).status_code == 404
    assert (await api.delete("/api/subscriptions/missing")).status_code == 404
    assert (await api.post("/api/reports/missing/feedback", json={})).status_code == 404
    assert not db.list_reports()
    with pytest.raises(TaskUnavailable):
        TaskRunner().subscribe("missing")


async def test_scope_restore_reconnect_feedback_and_subscription(api):
    subscription = (await api.post("/api/subscriptions", json={"query": "Notion vs Obsidian"})).json()
    task = (await api.post("/api/tasks", json={"query": "Notion vs Obsidian", "mode": "quick",
                                          "subscription_id": subscription["sub_id"]})).json()
    tid = task["taskId"]
    detail = (await api.get(f"/api/tasks/{tid}")).json()
    assert detail["clarifyQuestions"] == task["clarifyQuestions"]
    assert detail["query"] == "Notion vs Obsidian"
    assert (await api.post(f"/api/tasks/{tid}/clarify", json={"answers": {
        "competitors": ["Obsidian"], "_mode": "expert", "_subscription_id": "bogus"}})).status_code == 200
    first = await api.get(f"/api/tasks/{tid}/stream")
    assert "event: done" in first.text
    report = db.list_reports()[0]
    rid = report["id"]
    assert db.get_report(rid)["brands"] == ["Notion", "Obsidian"]
    assert db.get_report(rid)["mode"] == "quick"
    second = await api.get(f"/api/tasks/{tid}/stream")
    assert "event: done" in second.text and rid in second.text
    assert len(db.list_reports()) == 1
    detail = (await api.get(f"/api/tasks/{tid}")).json()
    assert detail["reportId"] == rid and detail["terminalSeq"] > 1
    assert (await api.get(f"/api/tasks/{tid}/stream?after={detail['terminalSeq']}")).text == ""
    assert (await api.get(f"/api/tasks/{tid}/stream", headers={"Last-Event-ID": str(detail["terminalSeq"])})).text == ""
    assert (await api.get(f"/api/tasks/{tid}/stream?after=-1")).status_code == 422
    assert (await api.get(f"/api/tasks/{tid}/stream", headers={"Last-Event-ID": "bad"})).status_code == 422
    assert (await api.get(f"/api/tasks/{tid}/stream", headers={"Last-Event-ID": "-1"})).status_code == 422
    assert (await api.post(f"/api/tasks/{tid}/clarify", json={"answers": {}})).status_code == 409
    saved_sub = db.get_subscription(subscription["sub_id"])
    assert saved_sub["run_count"] == 1 and saved_sub["last_report_id"] == rid
    assert (await api.patch(f"/api/reports/{rid}", json={"title": "Renamed", "starred": True})).status_code == 200
    feedback = await api.post(f"/api/reports/{rid}/feedback", json={"edited_blocks": 1, "total_blocks": 3})
    assert feedback.json()["ok"] and feedback.json()["report"]["title"] == "Renamed"
    refined = await api.post(f"/api/reports/{rid}/refine", json={"section_id": "summary", "annotations": ["Explain gaps"]})
    assert refined.json()["ok"] and refined.json()["report"]["subtitle"].startswith("[MOCK]")
    assert db.list_reports()[0]["starred"]
    assert db._connect().execute("SELECT task_id FROM reports WHERE report_id=?", (rid,)).fetchone()[0] == tid
    assert (await api.post(f"/api/reports/{rid}/feedback", json={"edited_blocks": 5, "total_blocks": 1})).status_code == 422
    assert (await api.delete(f"/api/reports/{rid}")).status_code == 200
    assert not db.list_reports() and not db.query_evidences() and not db.get_traces_by_report(rid)
    assert not db.get_subscription(subscription["sub_id"])["last_report_id"]
    assert (await api.get(f"/api/tasks/{tid}/stream")).status_code == 410


async def test_two_subscribers_share_job_and_disconnected_subscriber_does_not_cancel(offline):
    started, finish = asyncio.Event(), asyncio.Event()
    calls = []
    async def fake(tid):
        calls.append(tid)
        yield {"type": "progress", "data": {"percent": 1}}
        started.set()
        await finish.wait()
        db.save_report({"id": "r_single", "title": "One report"}, tid)
        db.mark_task_done(tid, "r_single")
        yield {"type": "done", "data": {"reportId": "r_single"}}
    task = pipeline.create_task("Notion vs Obsidian", "quick")
    tid = task["taskId"]
    runner = TaskRunner(fake)
    one, two = runner.subscribe(tid), runner.subscribe(tid)
    try:
        event = await anext(one)
        await started.wait()
        assert event["id"] == 1
        await one.aclose()
        resumed = runner.subscribe(tid, after=1)
        finish.set()
        events = [event async for event in two]
        replay = [event async for event in resumed]
        assert [event["id"] for event in events] == [1, 2]
        assert [event["id"] for event in replay] == [2]
        assert calls == [tid] and len(db.list_reports()) == 1 and not runner.jobs
        # A fresh runner after restart serves the durable terminal event.
        terminal = [e async for e in TaskRunner(fake).subscribe(tid)]
        assert terminal[0]["id"] == 2 and terminal[0]["type"] == "done"
    finally:
        finish.set()
        await runner.close()


async def test_failure_and_shutdown_are_terminal_and_not_retried(offline):
    calls = []
    async def failing(tid):
        calls.append(tid)
        yield {"type": "progress", "data": {}}
        raise RuntimeError("Provider unavailable")
    tid = pipeline.create_task("Notion", "quick")["taskId"]
    runner = TaskRunner(failing)
    events = [e async for e in runner.subscribe(tid)]
    assert events[-1]["type"] == "error" and db.get_task(tid)["status"] == "failed"
    assert [e async for e in runner.subscribe(tid)][0]["type"] == "error"
    assert calls == [tid] and not db.list_reports()
    async def waiting(tid):
        yield {"type": "progress", "data": {}}
        await asyncio.Event().wait()
    tid = pipeline.create_task("Obsidian", "quick")["taskId"]
    runner = TaskRunner(waiting)
    stream = runner.subscribe(tid)
    await anext(stream)
    await runner.close()
    assert db.get_task(tid)["status"] == "interrupted"
    assert [e async for e in runner.subscribe(tid)][0]["type"] == "error"
    await stream.aclose()


async def test_restart_marks_abandoned_running_tasks(offline):
    tid = pipeline.create_task("Notion", "quick")["taskId"]
    assert db.claim_task(tid)
    from app import main
    async with main.lifespan(main.app):
        assert db.get_task(tid)["status"] == "interrupted"
    assert "restart" in db.get_task(tid)["error"]


async def test_shutdown_before_worker_start_releases_reserved_job(offline):
    tid = pipeline.create_task("Notion", "quick")["taskId"]
    runner = TaskRunner()
    stream = runner.subscribe(tid)
    await runner.close()
    assert db.get_task(tid)["status"] == "interrupted" and not runner.jobs
    assert [e async for e in stream][-1]["type"] == "error"


async def test_fatal_model_errors_never_save_report(api, monkeypatch):
    from app.core.config import Settings
    from app.core.ratelimit import DailyQuotaExhausted
    tid = pipeline.create_task("Notion vs Obsidian", "quick")["taskId"]
    def fatal(*args, **kwargs):
        raise DailyQuotaExhausted("Daily quota exhausted")
    monkeypatch.setattr(pipeline, "chat_json", fatal)
    events = await api.get(f"/api/tasks/{tid}/stream")
    assert "event: error" in events.text and "event: done" not in events.text
    assert db.get_task(tid)["status"] == "failed" and not db.list_reports()
    for code in (401, 403, 429):
        req = httpx.Request("POST", "https://models.test/chat/completions")
        error = httpx.HTTPStatusError("Authentication/quota failure", request=req,
                                     response=httpx.Response(code, request=req))
        def auth(*args, **kwargs):
            raise error
        monkeypatch.setattr(pipeline, "chat_json", auth)
        with pytest.raises(httpx.HTTPStatusError):
            pipeline._plan_research("Notion", {})
    monkeypatch.setattr(pipeline, "_settings", Settings(_env_file=None, llm_provider="openai", openai_api_key=""))
    assert (await api.post("/api/tasks", json={"query": "Notion"})).status_code == 503


async def test_entire_failed_generation_is_not_reported_as_success(api, monkeypatch):
    tid = pipeline.create_task("Notion vs Obsidian", "quick")["taskId"]
    monkeypatch.setattr(pipeline, "_write_single_section", lambda *a, **kw: {
        "paragraphs": ["This section could not be generated."], "highlights": [], "key_takeaway": ""})
    events = await api.get(f"/api/tasks/{tid}/stream")
    assert "All report sections failed" in events.text and "event: done" not in events.text
    assert not db.list_reports()
