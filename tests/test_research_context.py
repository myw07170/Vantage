"""Regressions from the October 13 real-model report, without live services."""
import datetime as dt
import json
from pathlib import Path

import pytest

from app.core import db, llm, orchestrator as pipeline, trace, verify
from app.core.audit import evaluate_quality
from app.core.credibility import freshness_days, score_evidence
from app.core.evidence_context import select_evidence, evidence_digest
from app.core.models import Evidence


FIXTURE = json.loads((Path(__file__).parent / "fixtures/research_regression.json").read_text(encoding="utf-8"))


def evidence(brand, i, text="Product documentation."):
    return Evidence(f"e_{i:08x}", f"https://{brand.lower()}.test/{i}", "web", text,
                    text[:280], "2026-10-13T18:34:47Z", 40, "collector",
                    brand=brand, domain=f"{brand.lower()}.test", full_text=text)


def test_confirmation_locks_products_and_preserves_primary(offline, monkeypatch):
    task = pipeline.create_task("Notion vs Obsidian")
    tid = task["taskId"]
    assert not pipeline.submit_clarify(tid, {"competitors": ["Notion", "Obsidian"]})["ok"]
    assert db.get_task(tid)["status"] == "created"
    assert not pipeline.submit_clarify(tid, {"competitors": ["Obsidian", "Cursor"], "scope_confirmed": True})["ok"]
    assert pipeline.submit_clarify(tid, {"competitors": ["Notion", "Obsidian"], "scope_confirmed": True})["ok"]
    monkeypatch.setattr(pipeline, "chat_json", lambda *a, **kw: {
        "brands": FIXTURE["incorrect_brands"], "focus": ["Market share"], "search_angles": ["features"],
    })
    plan = pipeline._plan_research("Notion vs Obsidian", db.get_task(tid)["clarifications"])
    assert plan["brands"] == ["Notion", "Obsidian"]


def test_category_and_failed_discovery_require_explicit_products(offline, monkeypatch):
    monkeypatch.setattr(pipeline, "chat_json", lambda *a, **kw: None)
    task = pipeline.create_task("What are the AI coding assistant market trends?")
    assert any(q["id"] == "competitors" for q in task["clarifyQuestions"])
    tid = task["taskId"]
    for products in ([], ["AI coding assistant market", "Cursor"], ["AI Coding Assistant", "Cursor"]):
        assert not pipeline.submit_clarify(tid, {"competitors": products, "scope_confirmed": True})["ok"]
    assert pipeline.submit_clarify(tid, {"competitors": FIXTURE["confirmed_products"], "scope_confirmed": True})["ok"]
    assert pipeline._plan_research("market trends", db.get_task(tid)["clarifications"])["brands"] == FIXTURE["confirmed_products"]


def test_mock_does_not_guess_products_from_a_market_question(offline):
    query = "What are the key trends and leading players in the AI coding assistant market in 2026?"
    task = pipeline.create_task(query)
    scope = db.get_task(task["taskId"])["clarifications"]["_scope"]
    assert scope["subject_type"] == "category"
    assert not scope["competitors"]


def test_later_products_and_relevant_citations_reach_model_context(offline, monkeypatch):
    sources = [evidence("First", i, "General product documentation.") for i in range(40)]
    sources += [evidence("Later", 100 + i, "Pricing: paid annual plan is USD 10 per seat.") for i in range(6)]
    selected = select_evidence(sources, brands=["First", "Later"], dimensions=["Pricing"], limit=20)
    assert sum(e.brand == "Later" for e in selected) == 6
    priority = evidence("First", 999, "Pricing for the enterprise plan.")
    sources.append(priority)
    calls = []
    def complete(messages, **kw):
        calls.append((messages, kw))
        return {"paragraphs": ["A complete sourced finding."], "claims": []}
    monkeypatch.setattr(pipeline, "chat_json", complete)
    pipeline._write_single_section("pricing", "Pricing", "compare", ["First", "Later"],
        ["Pricing strategy"], sources, [{"field": "pricing_model", "text": "Enterprise price.",
        "evidence_ids": [priority.evidence_id], "confidence": "low"}], {}, "test")
    prompt = calls[0][0][-1]["content"]
    ids = calls[0][1]["evidence_ids"]
    assert priority.evidence_id in ids and "USD 10" in prompt
    assert any(e.evidence_id in ids for e in sources if e.brand == "Later")
    assert len(ids) <= 20


def test_context_persists_and_legacy_reports_fall_back(offline):
    source = evidence("Notion", 7, "Beginning. " + "Detailed pricing context. " * 90)
    db.save_report({"id": "r_context", "evidence": [source.to_dict()], "sections": []})
    saved = db.get_report("r_context")["evidence"][0]
    assert saved["full_text"] == source.full_text
    assert saved["excerpt"] != saved["full_text"]
    assert "Detailed pricing context" in evidence_digest([saved])
    saved.pop("full_text")
    saved.pop("published_at")
    assert saved["excerpt"] in evidence_digest([saved])
    assert "published: unknown" in evidence_digest([saved])


def test_vendor_provenance_and_publication_dates(offline):
    wrong = FIXTURE["misclassified_source"]
    assert pipeline._source_type(wrong["source_url"], "GitHub Copilot") == "web"
    assert pipeline._source_type("https://www.notion.com/pricing", "Notion") == "official"
    assert pipeline._source_type("https://notion.com.evil.test/pricing", "Notion") == "web"
    assert pipeline._source_type("https://random-vendor.test/pricing", "Unknown") == "web"
    assert pipeline._source_type("https://unknown.test/investor/annualreport", "Unknown") == "web"
    assert pipeline._source_type("https://reuters.com.evil.test/article", "Notion") == "web"
    assert pipeline._source_type("https://github.com/someone/copilot-notes", "GitHub Copilot") == "web"
    assert pipeline._source_type("https://github.com/features/copilot", "GitHub Copilot") == "official"
    assert pipeline._source_type("https://publish.obsidian.md/someone/note", "Obsidian") == "web"
    assert freshness_days("") is None
    yesterday = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat()
    assert freshness_days(yesterday) == 1
    result = pipeline._collect_brand("Notion", ["features"], "collector", 4, "month", set())
    assert result["evidences"]
    assert all(e.published_at is None and e.freshness_days is None for e in result["evidences"])
    base = score_evidence("https://example.test", "web")
    assert base < score_evidence("https://example.test", "web", captured_at=yesterday, has_publish_date=True)


def test_missing_dimensions_stay_missing():
    claims = [{"field": "feature_tree", "confidence": "high"}]
    report = evaluate_quality([], ["Feature comparison", "Market share", "Unknown custom question"], claims, [], {})
    assert report.coverage_by_dimension == {
        "Feature comparison": True, "Market share": False, "Unknown custom question": False,
    }


def test_complete_paragraph_is_not_truncated_and_reviewer_sees_full_body(offline, monkeypatch):
    paragraph = FIXTURE["complete_paragraph"]
    assert len(paragraph) > 700
    sections = {"summary": {"paragraphs": [paragraph], "key_takeaway": "A complete takeaway."}}
    titles = {"summary": "Summary"}
    cleaned, rules = verify.check_sections(sections, titles, {"e_40b9cbe1"}, min_paragraphs=1)
    assert not any(f.kind == "truncated" for f in rules.open)
    prompts = []
    def review(messages, **kwargs):
        prompts.append(messages[-1]["content"])
        return {"verdict": "pass", "findings": [], "scores": {"Evidence support": 80}}
    monkeypatch.setattr(llm, "chat_json", review)
    result = verify.llm_report_review("compare", ["A", "B"], cleaned, titles, ["summary"], [], rules)
    assert paragraph in prompts[0] and result["review_complete"]
    assert "SUMMARY ONLY" in verify._report_digest(sections, titles, ["summary"])
    _, broken = verify.check_sections({"summary": {"paragraphs": ["The actual paragraph ends before it can explain why the"]}}, titles, set(), min_paragraphs=1)
    assert any(f.kind == "truncated" for f in broken.open)


@pytest.mark.parametrize("status", ["open", "unavailable", "passed"])
async def test_rewrite_requires_successful_recheck(offline, monkeypatch, status):
    def write(*args, **kwargs):
        sid, source = args[0], args[5][0].evidence_id
        return {"paragraphs": [f"{sid} supported source note {i} [{source}]." for i in range(3)],
                "key_takeaway": f"{sid} source notes are bounded to collected evidence.", "highlights": []}
    monkeypatch.setattr(pipeline, "_write_single_section", write)
    def review(*args, **kwargs):
        target_ids = args[11] if len(args) > 11 else None
        finding = {"section_id": "summary", "severity": "major", "kind": "unsupported",
                   "detail": "The original statement is unsupported.", "fix": "Use only supported facts."}
        return {"verdict": "pass" if target_ids and status == "passed" else "revise",
                "findings": [] if target_ids and status != "open" else [finding],
                "review_complete": status != "unavailable" or not target_ids,
                "section_status": {sid: status for sid in (target_ids or [])}, "review": "Review result.", "scores": {}}
    monkeypatch.setattr(pipeline, "llm_report_review", review)
    tid = pipeline.create_task("Notion vs Obsidian", "quick")["taskId"]
    assert pipeline.submit_clarify(tid, {"competitors": ["Notion", "Obsidian"], "scope_confirmed": True})["ok"]
    events = [e async for e in pipeline.run_pipeline(tid)]
    rid = next(e["data"]["reportId"] for e in events if e["type"] == "done")
    result = db.get_report(rid)["verify_review"]
    assert result["recheck_status"]["summary"] == status
    remains = any(f["detail"] == "The original statement is unsupported." for f in result["findings"])
    assert remains == (status != "passed")
    if status != "passed":
        assert result["verdict"] == "flagged"


def test_trace_carries_actual_context_ids(offline):
    trace.set_context("t_ids", "analyst", "analyze", "test")
    llm.chat_json([], task_kind="json", mock_context={"result": {}}, evidence_ids=["e_00000001"])
    assert trace.get_trace("t_ids")[-1]["evidence_ids"] == ["e_00000001"]
    trace.cleanup("t_ids")


def test_reader_refinement_appends_trace_and_invalidates_old_review(offline):
    source = evidence("Notion", 1)
    db.save_report({"id": "r_refine_trace", "brands": ["Notion", "Obsidian"],
                   "evidence": [source.to_dict()], "trace": [{"span_id": "sp_old", "seq": 999999}],
                   "sections": [{"id": "summary", "title": "Summary", "paragraphs": ["Original prose."]}],
                   "verify_review": {"verdict": "pass", "review_complete": True}})
    result = pipeline.refine_section("r_refine_trace", "summary", ["Explain the source gap."])
    assert result["ok"]
    saved = db.get_report("r_refine_trace")
    assert saved["trace"][-1]["evidence_ids"] == [source.evidence_id]
    assert saved["trace"][0] == {"span_id": "sp_old", "seq": 999999}
    assert saved["trace"][-1]["seq"] == 1000000
    assert db.get_traces_by_report("r_refine_trace")[-1]["evidence_ids"] == [source.evidence_id]
    assert saved["verify_review"]["verdict"] == "flagged"
    assert saved["verify_review"]["recheck_status"]["summary"] == "unavailable"

