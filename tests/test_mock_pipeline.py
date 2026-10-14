"""Run actual research orchestration against deterministic collection fixtures."""
from __future__ import annotations

import re
import inspect

import pytest

from app.core import db, llm, orchestrator as pipeline


async def _run(mode="quick", query="Notion vs Obsidian"):
    task = pipeline.create_task(query, mode)
    assert pipeline.submit_scope(task["taskId"], "yes", task["scopeRevision"])["ok"]
    confirmed = pipeline.task_details(db.get_task(task["taskId"]))
    confirmed = pipeline.submit_clarify(task["taskId"], {
        "competitors": ["Notion", "Obsidian"],
        "focus": ["Feature comparison", "Pricing strategy", "User sentiment"],
    }, revision=confirmed["clarificationRevision"])
    assert confirmed["ok"]
    confirmed = pipeline.submit_clarify(task["taskId"], {"market": "No preference"}, revision=confirmed["clarificationRevision"])
    assert confirmed["ok"]
    assert pipeline.submit_clarify(task["taskId"], {}, action="start", revision=confirmed["clarificationRevision"])["ok"]
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
    assert {"quick": 6, "deep": 7, "expert": 8}[mode] == len(report["experts"])
    assert {"L3-001", "L3-002", "L3-003", "L1-025", "L1-030"} <= set(report["experts"])
    assert report["is_mock"] is True and report["llm_provider"] == "mock"
    assert report["subtitle"].startswith("[MOCK] Simulated report")
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


async def test_industry_methods_survive_pipeline_rework_reload_and_refinement(offline):
    _, report = await _run("deep", "Notion vs Obsidian for cloud infrastructure")
    modules = report["industry_modules"]
    assert modules and modules[0]["id"] == "cloud-infrastructure"
    assert report["brands"] == ["Notion", "Obsidian"]
    assert all(e.startswith("L") for e in report["experts"])
    assert not ({m["legacy_expert_id"] for m in modules} & set(report["experts"]))
    for brand in report["brands"]:
        assert brand + " " + modules[0]["search_angles"][0] in offline.searches
    for kind in ("dispatch", "analyze", "structured", "sentiment", "quotes", "quality_review", "write_section", "report_review", "sentiment_narrative"):
        matching = [messages for task_kind, messages in offline.prompts if task_kind == kind]
        assert matching, kind
        assert all(modules[0]["checks"][0] in "\n".join(m["content"] for m in messages) for messages in matching)
    assert db.get_report(report["id"])["industry_modules"] == modules
    snapshot_check = "Check the frozen method used when this report was created."
    report["industry_modules"][0]["checks"] = [snapshot_check]
    db.save_report(report)
    assert pipeline.refine_section(report["id"], "summary", ["Review the cloud cost assumptions"])["ok"]
    assert offline.prompts[-1][0] == "refine_section"
    assert snapshot_check in "\n".join(m["content"] for m in offline.prompts[-1][1])
    assert db.get_report(report["id"])["industry_modules"][0]["checks"] == [snapshot_check]
    assert sum(kind == "plan" for kind, _ in offline.operations) == 1
    assert sum(kind == "dispatch" for kind, _ in offline.operations) == 1


async def test_historical_report_without_modules_can_be_refined(offline):
    _, report = await _run()
    report.pop("industry_modules", None)
    report["experts"].append("L1-008")
    db.save_report(report)
    result = pipeline.refine_section(report["id"], "summary", ["Explain the evidence gaps"])
    assert result["ok"] and "L1-008" in result["report"]["experts"]
    assert "industry_modules" not in result["report"]


async def test_no_evidence_reports_collection_failure(offline, monkeypatch):
    monkeypatch.setattr(pipeline, "multi_search", lambda *args, **kwargs: [])
    monkeypatch.setattr(pipeline, "api_platforms", lambda: [])
    events, report = await _run()
    assert report is None
    assert any(e["type"] == "error" and "No usable evidence" in e["data"]["message"] for e in events)
    assert not db.list_reports()


async def test_refine_and_rename_keep_mock_marker(offline):
    _, report = await _run()
    # Normalize the historical localized label only during an explicit refinement.
    report["subtitle"] = report["subtitle"].replace("[MOCK] Simulated report", "[MOCK] 模拟报告", 1)
    db.save_report(report)
    result = pipeline.refine_section(report["id"], "summary", ["Explain the missing pricing evidence"])
    assert result["ok"] and result["section"]["refined"]
    assert result["report"]["subtitle"].startswith("[MOCK] Simulated report")
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
