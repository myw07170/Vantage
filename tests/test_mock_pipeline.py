"""Run actual research orchestration against deterministic collection fixtures."""
from __future__ import annotations

import re
import inspect

import pytest

from app.core import db, llm, orchestrator as pipeline


async def _run(mode="quick", query="Notion vs Obsidian", brands=None):
    task = pipeline.create_task(query, mode)
    assert pipeline.submit_scope(task["taskId"], "yes", task["scopeRevision"])["ok"]
    confirmed = pipeline.task_details(db.get_task(task["taskId"]))
    confirmed = pipeline.submit_clarify(task["taskId"], {
        "competitors": brands or ["Notion", "Obsidian"],
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
            "write_section", "writing_plan", "writing_plan_review", "writing_edit", "writing_assertions",
            "quality_review", "report_review"} <= {
                kind for kind, _ in offline.operations}
    assert report["audit_review"]["before"]["verdict"] == "rework"
    assert report["audit_review"]["rework_rounds"] == {"quick": 2, "deep": 3, "expert": 5}[mode]
    assert report["audit_review"]["status"] == "simulated"
    assert report["audit_review"]["after"]["simulated"]
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
    for kind in ("dispatch", "analyze", "structured", "sentiment", "quotes", "quality_review", "write_section", "report_review", "writing_plan", "writing_notes", "writing_edit", "writing_assertions"):
        matching = [messages for task_kind, messages in offline.prompts if task_kind == kind]
        assert matching, kind
        assert all(modules[0]["checks"][0] in "\n".join(m["content"] for m in messages) for messages in matching)
    assert db.get_report(report["id"])["industry_modules"] == modules
    snapshot_check = "Check the frozen method used when this report was created."
    report["industry_modules"][0]["checks"] = [snapshot_check]
    db.save_report(report)
    assert pipeline.refine_section(report["id"], "summary", ["Review the cloud cost assumptions"])["ok"]
    refined_prompts = [p for k, p in offline.prompts if k == "refine_section"]
    assert snapshot_check in "\n".join(m["content"] for m in refined_prompts[-1])
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


def _strict_gate(monkeypatch):
    # Keep completions offline, but exercise the production gate policy.
    monkeypatch.setattr(pipeline, "_settings", pipeline._settings.model_copy(
        update={"llm_provider": "qwen", "qwen_api_key": "offline-test"}))


def _review_result(findings, previous=()):
    return {"verdict": "rework" if findings else "pass", "scores": {"Evidence sufficiency": 70},
            "review": "Test evidence review", "findings": findings,
            "issues": [i["reason"] for i in findings], "suggestions": [i["fix"] for i in findings],
            "resolutions": [{"issue_id": i["issue_id"], "status": "corrected", "reason": "Current evidence supports the corrected answer."}
                            for i in previous], "simulated": False}


@pytest.mark.parametrize("mode,limit", [("quick", 2), ("deep", 3), ("expert", 5)])
async def test_strict_gate_exhausts_exact_limit_and_never_writes(offline, monkeypatch, mode, limit):
    from app.core.audit import issue
    _strict_gate(monkeypatch)
    calls = []
    def review(*args, **kwargs):
        calls.append(kwargs)
        return _review_result([issue("claim", "Unverified critical comparison", brand="Notion")])
    monkeypatch.setattr(pipeline, "llm_quality_review", review)
    events, report = await _run(mode)
    assert report is None and len(calls) == limit + 1
    assert any(e["type"] == "error" and e["data"]["code"] == "audit_blocked" for e in events)
    assert not any(kind == "write_section" for kind, _ in offline.operations)
    tid = db._connect().execute("SELECT task_id FROM tasks").fetchone()[0]
    snapshot = db.get_task_audit(tid)
    assert snapshot["audit_review"]["status"] == "blocked"
    assert snapshot["audit_review"]["rework_rounds"] == limit
    assert len(snapshot["audit_review"]["history"]) == limit + 1
    assert snapshot["evidence"] and snapshot["trace"] and snapshot["analysis"]
    assert not db.list_reports()


async def test_collect_only_repair_runs_analysis_and_structured_once_then_stops(offline, monkeypatch):
    from app.core.audit import issue
    from app.core.models import Evidence
    _strict_gate(monkeypatch)
    reviews = []
    def review(*args, **kwargs):
        reviews.append(kwargs)
        findings = [issue("source", "Need a second source", brand="Obsidian", dimension="Pricing", action="collect",
                          fix="Find original annual subscription per-seat billing terms")] if len(reviews) == 1 else []
        return _review_result(findings, kwargs.get("previous_issues", []))
    original = pipeline._collect_brand
    collects = []
    def collect(*args, **kwargs):
        if len(args) > 8:
            collects.append(args)
            ev = Evidence("e_repair", "https://independent.example/obsidian", "news", "Obsidian price", "Published price details", "2026-10-14", 70, "L1-025", brand="Obsidian", full_text="New pricing evidence", content_kind="body")
            return {"evidences": [ev], "images": [], "found": 1}
        return original(*args, **kwargs)
    monkeypatch.setattr(pipeline, "llm_quality_review", review)
    monkeypatch.setattr(pipeline, "_collect_brand", collect)
    events, report = await _run("deep")
    assert report and len(reviews) == 2 and len(collects) == 1
    assert report["audit_review"]["rework_rounds"] == 1
    assert report["audit_review"]["issues_resolved"] == 1
    for kind in ("analyze", "structured"):
        calls = [ctx for k, ctx in offline.operations if k == kind]
        assert len(calls) == 2
        assert "e_repair" in {e["evidence_id"] for e in calls[-1]["evidence"]}
        prompts = [messages for k, messages in offline.prompts if k == kind]
        assert "Need a second source" in str(prompts[-1])
    snapshots = [e for e in events if e["type"] == "message" and e["data"].get("kind") == "analysis_snapshot"]
    assert len(snapshots) == 1 and snapshots[0]["data"]["claims"] == report["claims"]
    assert collects[0][1] and any("Pricing" in angle for angle in collects[0][1])
    assert any("annual subscription" in angle for angle in collects[0][1])
    assert set(collects[0][8].values()) == {"Pricing strategy"}


async def test_each_round_reviews_again_and_uses_latest_findings(offline, monkeypatch):
    from app.core.audit import issue
    _strict_gate(monkeypatch)
    reviews = []
    def review(*args, **kwargs):
        n = len(reviews)
        reviews.append(kwargs)
        findings = [issue("claim", f"Problem from review {n}", brand="Notion")] if n < 2 else []
        return _review_result(findings, kwargs.get("previous_issues", []))
    monkeypatch.setattr(pipeline, "llm_quality_review", review)
    _, report = await _run("expert")
    assert report and len(reviews) == 3 and report["audit_review"]["rework_rounds"] == 2
    for kind in ("analyze", "structured"):
        prompts = [str(p) for k, p in offline.prompts if k == kind]
        assert "Problem from review 0" in prompts[1]
        assert "Problem from review 1" in prompts[2]


async def test_all_affected_brands_are_recollected_even_if_no_new_evidence(offline, monkeypatch):
    from app.core.audit import issue
    _strict_gate(monkeypatch)
    brands = ["Notion", "Obsidian", "Roam", "Logseq"]
    calls, reviews = [], []
    original = pipeline._collect_brand
    def collect(*args, **kwargs):
        if len(args) > 8:
            calls.append(args[0])
            return {"evidences": [], "images": [], "found": 0}
        return original(*args, **kwargs)
    def review(*args, **kwargs):
        reviews.append(kwargs)
        problems = [issue("source", "Need sources", brand=b, dimension="Pricing", action="collect") for b in brands] if len(reviews) == 1 else []
        return _review_result(problems, kwargs.get("previous_issues", []))
    monkeypatch.setattr(pipeline, "_collect_brand", collect)
    monkeypatch.setattr(pipeline, "llm_quality_review", review)
    _, report = await _run("quick", brands=brands)
    assert report and set(calls) == set(brands)
    assert len([k for k, _ in offline.operations if k == "analyze"]) >= 2


async def test_only_minor_issues_can_ship_after_limit(offline, monkeypatch):
    from app.core.audit import issue
    _strict_gate(monkeypatch)
    monkeypatch.setattr(pipeline, "llm_quality_review", lambda *a, **k:
                        _review_result([issue("wording", "Clarify a nonessential label", severity="low")]))
    _, report = await _run()
    assert report and report["audit_review"]["status"] == "pass_with_warnings"
    assert report["audit_review"]["issues_resolved"] == 0
    assert all("Clarify a nonessential label" in str(p) for k, p in offline.prompts if k == "write_section")


@pytest.mark.parametrize("failure", [TimeoutError("review timed out"), RuntimeError("review quota exhausted")])
async def test_review_failure_preserves_latest_material_without_writing(offline, monkeypatch, failure):
    _strict_gate(monkeypatch)
    def broken(*args, **kwargs):
        raise failure
    monkeypatch.setattr(pipeline, "llm_quality_review", broken)
    events, report = await _run()
    assert not report
    assert any(e["type"] == "error" and e["data"].get("code") == "audit_unavailable" for e in events)
    tid = db._connect().execute("SELECT task_id FROM tasks").fetchone()[0]
    snapshot = db.get_task_audit(tid)
    assert snapshot["audit_review"]["status"] == "unavailable"
    assert snapshot["evidence"] and snapshot["structured"] and snapshot["sentiment"]
    assert not any(k == "write_section" for k, _ in offline.operations)
