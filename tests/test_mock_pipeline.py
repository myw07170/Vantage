"""Run actual research orchestration against deterministic collection fixtures."""
from __future__ import annotations

import re
import inspect

import pytest

from app.core import db, llm, orchestrator as pipeline


async def _run(mode="quick"):
    task = pipeline.create_task("Notion vs Obsidian", mode)
    pipeline.submit_clarify(task["taskId"], {
        "competitors": ["Notion", "Obsidian"],
        "focus": ["Feature comparison", "Pricing strategy", "User sentiment"],
    })
    events = [ev async for ev in pipeline.run_pipeline(task["taskId"])]
    done = next((ev for ev in events if ev["type"] == "done"), None)
    report = db.get_report(done["data"]["reportId"]) if done else None
    return events, report


def _assert_citations(report):
    valid = {e["evidence_id"] for e in report["evidence"]}
    assert all(set(c["evidence_ids"]) <= valid for c in report["claims"])
    for section in report["sections"]:
        assert set(section.get("source_evidence_ids", [])) <= valid
        for paragraph in section.get("paragraphs", []):
            assert set(re.findall(r"\[(e_[0-9a-f]+)\]", paragraph)) <= valid


@pytest.mark.parametrize("mode", ["quick", "deep", "expert"])
async def test_all_modes_complete_with_real_pipeline(offline, mode):
    events, report = await _run(mode)
    assert not [e for e in events if e["type"] == "error"]
    assert report is not None and report["mode"] == mode
    assert report["is_mock"] is True and report["llm_provider"] == "mock"
    assert report["subtitle"].startswith("[MOCK] 模拟报告")
    assert len(report["evidence"]) >= 8 and len(report["claims"]) >= 3
    assert all(section.get("paragraphs") for section in report["sections"])
    assert offline.searches and offline.fetches
    assert report["sentiment"]["sample_size"] == 4
    assert report["trace"]
    model_spans = [s for s in report["trace"] if s["model"].startswith("mock:")]
    assert model_spans and all(s["total_tokens"] == 0 for s in model_spans)
    assert {"scope", "plan", "dispatch", "analyze", "structured", "sentiment", "quotes",
            "write_section", "sentiment_narrative", "quality_review", "report_review"} <= {
                kind for kind, _ in offline.operations}
    assert report["audit_review"]["before"]["verdict"] == "rework"
    if mode != "quick":
        assert report["audit_review"]["rework_rounds"] >= 1
        assert any(e["type"] == "message" and e["data"].get("kind") == "rework" for e in events)
    _assert_citations(report)
    assert db.list_reports()[0]["subtitle"].startswith("[MOCK]")


async def test_no_evidence_reports_collection_failure(offline, monkeypatch):
    monkeypatch.setattr(pipeline, "multi_search", lambda *args, **kwargs: [])
    monkeypatch.setattr(pipeline, "api_platforms", lambda: [])
    events, report = await _run()
    assert report is None
    assert any(e["type"] == "error" and "No usable evidence" in e["data"]["message"] for e in events)
    assert not db.list_reports()


async def test_refine_and_rename_keep_mock_marker(offline):
    _, report = await _run()
    result = pipeline.refine_section(report["id"], "summary", ["Explain the missing pricing evidence"])
    assert result["ok"] and result["section"]["refined"]
    assert any("Reader annotations" in p for p in result["section"]["paragraphs"])
    db.update_report(report["id"], title="Renamed report", starred=True)
    saved = db.get_report(report["id"])
    assert saved["llm_provider"] == "mock" and saved["is_mock"]
    assert saved["subtitle"].startswith("[MOCK]")
    assert db.list_reports()[0]["subtitle"].startswith("[MOCK]")
    _assert_citations(saved)


async def test_mock_refine_marks_historical_real_report(offline):
    _, report = await _run()
    report["subtitle"] = "Previously generated with a real provider"
    report["llm_provider"] = "openai"
    report["is_mock"] = False
    db.save_report(report)
    assert pipeline.refine_section(report["id"], "summary", ["Review source coverage"])["ok"]
    saved = db.get_report(report["id"])
    assert saved["is_mock"] and saved["llm_provider"] == "mock"
    assert saved["subtitle"].startswith("[MOCK]")
    assert db.list_reports()[0]["subtitle"].startswith("[MOCK]")


async def test_verify_attempts_rewrite_and_keeps_rules(offline, monkeypatch):
    original = pipeline._write_single_section
    def defective(*args, **kwargs):
        output = original(*args, **kwargs)
        bound = inspect.signature(original).bind_partial(*args, **kwargs)
        if not bound.arguments.get("fix_directive"):
            output["paragraphs"] = ["This section could not be generated."]
        return output
    monkeypatch.setattr(pipeline, "_write_single_section", defective)
    _, report = await _run()
    rewrites = [ctx for kind, ctx in offline.operations if kind == "write_section" and ctx.get("fix_directive")]
    assert rewrites
    assert report["verify_review"]["rewritten_sections"]
    assert report["verify_review"]["rounds"] >= 1
    # Quick mode can only rewrite two sections; unresolved defects stay visible.
    assert report["verify_review"]["verdict"] == "flagged"
    assert report["verify_review"]["findings"]
    _assert_citations(report)


def test_empty_mock_analysis_and_structures_do_not_invent_data(offline):
    result = llm.chat_json([], task_kind="analyze", mock_context={"evidence": []})
    assert result["claims"] == result["pricing"] == result["market_share"] == []
    structured = llm.chat_json([], task_kind="structured", mock_context={"brands": ["Notion"], "evidence": []})
    assert structured["pricing_model"] == structured["user_persona"] == []
    assert all(not b["modules"] for b in structured["feature_tree"])


def test_health_and_ping_show_provider(offline, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "settings", pipeline._settings)
    assert main.health() == {"status": "ok", "llm_configured": True,
                             "llm_provider": "mock", "is_mock": True}
    ping = main.llm_ping()
    assert ping["ok"] and ping["reply"] == "ready" and ping["quota"] == {}
    assert ping["llm_provider"] == "mock" and ping["is_mock"]
