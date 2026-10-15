"""End-to-end contracts for dynamic reports, failed drafts and rewrites."""
import copy
import threading

import pytest

from app.core import db, llm_mock, orchestrator as pipeline
from app.core.writing import WritingError
from test_mock_pipeline import _run, _strict_gate, _review_result


async def test_dynamic_sections_components_title_and_material_usage_survive_reload(offline):
    _, report = await _run()
    assert report["writing_plan"]["version"] == 2
    assert report["title"] == report["writing_plan"]["title"]
    assert [s["id"] for s in report["sections"]] == [c["id"] for c in report["writing_plan"]["chapters"]]
    assert all(s["chapter_plan"]["author"] for s in report["sections"])
    assert any(c["kind"] == "sentiment" for s in report["sections"] for c in s["components"])
    assert not any(s["id"] in ("swot", "moat", "sentiment", "persp_user", "trace_note") for s in report["sections"])
    saved = db.get_report(report["id"])
    assert saved["writing_plan"] == report["writing_plan"]
    assert saved["research_analysis"] and saved["writing_assets"]
    tid = db._connect().execute("SELECT task_id FROM tasks").fetchone()[0]
    snapshot = db.get_task_audit(tid)
    assert snapshot["writing_status"] == "complete" and snapshot["drafts"]
    assert snapshot["material_usage"] and snapshot["writing_history"]


async def test_no_summary_or_legacy_theme_is_required_when_model_chooses_a_single_chapter(offline, monkeypatch):
    original = llm_mock._result
    def custom(kind, context):
        value = original(kind, context)
        if kind == "writing_plan":
            main = value["chapters"][1]
            main.update(id="budget_decision", title="The purchasing decision", answers=context["focus"],
                        target_words=context["target_words"], depends_on=[], components=[])
            value.update(title="How this team should evaluate the purchase", chapters=[main])
            value["unused_material"] = [{"id": u["unit_id"], "reason": "Not needed for the purchasing decision."}
                                        for u in context["units"] if u["kind"] not in ("claim", "evidence")]
        return value
    monkeypatch.setattr(llm_mock, "_result", custom)
    _, report = await _run()
    assert report and [s["id"] for s in report["sections"]] == ["budget_decision"]
    assert report["title"] == "How this team should evaluate the purchase"


async def test_unusable_plan_stops_before_writing_and_retains_research(offline, monkeypatch):
    original = pipeline.chat_json
    def bad(messages, **kwargs):
        if kwargs.get("task_kind") == "writing_plan":
            return {"title": "Broken", "brands": ["Unselected product"], "chapters": []}
        return original(messages, **kwargs)
    monkeypatch.setattr(pipeline, "chat_json", bad)
    events, report = await _run()
    assert report is None
    assert any(e["type"] == "error" and e["data"]["code"] == "write_planning_failed" for e in events)
    assert not any(k == "write_section" for k, _ in offline.operations)
    tid = db._connect().execute("SELECT task_id FROM tasks").fetchone()[0]
    assert db.get_task_audit(tid)["evidence"]
    assert db.get_task_audit(tid)["writing_status"] == "unavailable"
    attempts = [h for h in db.get_task_audit(tid)["writing_history"] if h["stage"] == "planning"]
    assert len(attempts) == 2 and attempts[0]["proposed_plan"] and attempts[1]["error"]


async def test_dependent_chapter_receives_actual_predecessor_and_summary_runs_last(offline, monkeypatch):
    original = llm_mock._result
    def dependency(kind, context):
        result = original(kind, context)
        if kind == "writing_plan":
            result["chapters"][2]["depends_on"] = [result["chapters"][1]["id"]]
        return result
    monkeypatch.setattr(llm_mock, "_result", dependency)
    _, report = await _run()
    calls = [ctx for kind, ctx in offline.operations if kind == "write_section"]
    body_position = next(i for i, c in enumerate(calls) if c["chapter"]["id"] == "question_1")
    dependent_position = next(i for i, c in enumerate(calls) if c["chapter"]["id"] == "question_2")
    summary_position = next(i for i, c in enumerate(calls) if c["chapter"]["role"] == "summary")
    assert body_position < dependent_position < summary_position
    assert calls[dependent_position]["completed"]["question_1"]["paragraphs"]
    assert report["writing_plan"]["chapters"][0]["role"] == "summary"  # display order differs from execution


async def test_serious_written_findings_are_rechecked_and_block_delivery_at_budget(offline, monkeypatch):
    _strict_gate(monkeypatch)
    monkeypatch.setattr(pipeline, "llm_quality_review", lambda *a, **k: _review_result([]))
    reviews = []
    def review(*args, **kwargs):
        sections = args[2]
        sid = next(s for s in sections if s != "summary")
        reviews.append(copy.deepcopy(sections))
        return {"verdict": "revise", "scores": {}, "review": "Unsupported comparison", "assertions": [],
                "findings": [{"section_id": sid, "severity": "major", "kind": "unsupported",
                              "detail": "This verdict lacks source support.", "fix": "Remove or correct it."}]}
    monkeypatch.setattr(pipeline, "llm_report_review", review)
    events, report = await _run()
    assert report is None and len(reviews) == 2  # initial + Quick's single repair round
    assert any(e["type"] == "error" and e["data"]["code"] == "verify_blocked" for e in events)
    tid = db._connect().execute("SELECT task_id FROM tasks").fetchone()[0]
    snapshot = db.get_task_audit(tid)
    assert snapshot["writing_status"] == "blocked" and snapshot["drafts"]
    assert snapshot["writing_verification"]["findings"]
    assert not db.list_reports()


async def test_report_review_failure_does_not_downgrade_to_rules_only(offline, monkeypatch):
    def fail(*args, **kwargs):
        raise WritingError("Source review output is incomplete")
    monkeypatch.setattr(pipeline, "llm_report_review", fail)
    events, report = await _run()
    assert not report
    assert any(e["type"] == "error" and e["data"]["code"] == "verify_unavailable" for e in events)
    tid = db._connect().execute("SELECT task_id FROM tasks").fetchone()[0]
    assert db.get_task_audit(tid)["drafts"] and db.get_task_audit(tid)["writing_status"] == "unavailable"


async def test_refinement_reads_complete_material_and_preserves_other_chapters(offline):
    _, report = await _run()
    before = copy.deepcopy(report["sections"])
    result = pipeline.refine_section(report["id"], "summary", ["Explain the purchasing tradeoff"])
    assert result["ok"]
    assert result["report"]["sections"][1:] == before[1:]
    assert any(k == "writing_assertions" for k, _ in offline.operations)
    assert result["section"]["refined"]


async def test_independent_chapters_actually_execute_concurrently(offline, monkeypatch):
    original = pipeline._write_single_section
    barrier = threading.Barrier(3, timeout=10)
    overlapped = []
    def parallel(*args, **kwargs):
        if args[0].startswith("question_") and not overlapped:
            barrier.wait()
        result = original(*args, **kwargs)
        if args[0].startswith("question_"):
            overlapped.append(args[0])
        return result
    monkeypatch.setattr(pipeline, "_write_single_section", parallel)
    _, report = await _run()
    assert report and len(set(overlapped)) == 3


async def test_repaired_body_refreshes_summary_and_rechecks_latest_actual_text(offline, monkeypatch):
    original = llm_mock._result
    write_counts = {}
    def marked(kind, context):
        result = original(kind, context)
        if kind == "write_section":
            sid = context["chapter"]["id"]
            write_counts[sid] = write_counts.get(sid, 0) + 1
            result["paragraphs"].append(f"Revision {write_counts[sid]} of {sid}.")
        return result
    monkeypatch.setattr(llm_mock, "_result", marked)
    reviews = []
    def review(*args, **kwargs):
        reviews.append(copy.deepcopy(args[2]))
        return {"verdict": "revise" if len(reviews) == 1 else "pass", "scores": {}, "review": "Test full review",
            "assertions": [], "findings": [{"section_id": "question_1", "severity": "major", "kind": "unsupported",
                "detail": "Revise the cost premise.", "fix": "Use the published cost."}] if len(reviews) == 1 else []}
    monkeypatch.setattr(pipeline, "llm_report_review", review)
    events, report = await _run()
    assert report and len(reviews) == 2
    assert "Revision 2 of question_1." in reviews[-1]["question_1"]["paragraphs"]
    summaries = [ctx for k, ctx in offline.operations if k == "write_section" and ctx["chapter"]["role"] == "summary"]
    assert "Revision 2 of question_1." in summaries[-1]["completed"]["question_1"]["paragraphs"]
    assert "Revision 3 of summary." in reviews[-1]["summary"]["paragraphs"]
    streamed = [e["data"]["draft"] for e in events if e["type"] == "message" and e["data"].get("kind") == "writing_draft"
                and e["data"].get("section_id") == "summary"]
    assert streamed[-1]["paragraphs"] == reviews[-1]["summary"]["paragraphs"]


async def test_historical_report_without_writing_metadata_keeps_existing_sections(offline):
    _, report = await _run()
    for key in ("writing_plan", "writing_assets", "material_usage", "research_analysis", "writing_assertions"):
        report.pop(key, None)
    for section in report["sections"]:
        for key in ("chapter_plan", "components", "written_assertions"):
            section.pop(key, None)
    before = copy.deepcopy(report["sections"])
    db.save_report(report)
    result = pipeline.refine_section(report["id"], "question_1", ["Retain the original pricing scope"])
    assert result["ok"] and "writing_plan" not in result["report"]
    assert result["report"]["sections"][0] == before[0]
    assert result["report"]["sections"][2:] == before[2:]
