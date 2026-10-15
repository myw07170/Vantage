"""Pre-write gate contracts: support, coverage, provenance and fail-closed review."""
import json
from types import SimpleNamespace

import pytest

from app.core import audit, llm, orchestrator as pipeline
from app.core.models import Evidence
from app.core.research_material import evidence_batches, merge_analysis


def evidence(i=0, brand="Acme", text=None, domain=None):
    text = text or f"Acme official plan {i} costs USD 12 per seat each month."
    return Evidence(f"e_{i}", f"https://{domain or 'acme.example'}/plans/{i}", "official",
                    "Acme pricing", text[:280], "2026-10-14", 80, "L1-025", brand=brand,
                    full_text=text, content_kind="body")


def claim(eid="e_0", text="Acme costs USD 12 per seat per month.", field="pricing_model"):
    return {"claim_id": "c_0", "text": text, "field": field, "brands": ["Acme"],
            "dimensions": ["Pricing"], "evidence_ids": [eid], "confidence": "low"}


@pytest.fixture
def reviewer(monkeypatch):
    monkeypatch.setattr(llm, "get_settings", lambda: SimpleNamespace(is_mock=False))
    calls = []
    controls = {"type": "fact", "official": True, "status": "supported"}

    def complete(messages, **kwargs):
        packet = json.loads(messages[-1]["content"])
        calls.append(packet)
        checks = []
        for unit in packet["items"]:
            ids = [s["evidence_id"] for s in unit["sources"]]
            status = controls["status"]
            if controls.get("transform"):
                status = controls["transform"](unit)
            checks.append({"check_id": unit["check_id"], "status": status,
                           "claim_type": "coverage" if unit["kind"] == "coverage" else controls["type"],
                           "severity": "high", "reason": "Checked against the supplied passages.",
                           "fix": "Collect independent support or remove the assertion.",
                           "evidence_ids": ids, "official_evidence_ids": ids if controls["official"] else []})
        return {"scores": {"Evidence sufficiency": 83}, "review": "Evidence checked.", "checks": checks,
                "resolutions": []}
    monkeypatch.setattr(llm, "chat_json", complete)
    return calls, controls


def review(evs, claims=None, focus=None, structured=None, analysis=None, searches=None):
    claims = [claim()] if claims is None else claims
    focus = ["Pricing"] if focus is None else focus
    qr = audit.evaluate_quality(["Acme"], focus, claims, evs, structured or {}, analysis=analysis, searches=searches)
    return audit.llm_quality_review("Compare Acme", ["Acme"], focus, claims, structured or {}, qr,
                                    evidences=evs, analysis=analysis, searches=searches), qr


def test_one_verified_original_official_fact_can_pass_without_high_confidence(reviewer):
    result, qr = review([evidence()])
    assert result["verdict"] == "pass" and not result["simulated"]
    assert qr.confidence_ratio == 0


def test_source_type_official_does_not_itself_prove_official_ownership(reviewer):
    reviewer[1]["official"] = False
    result, _ = review([evidence()])
    assert result["verdict"] == "rework"
    assert any(i["action"] == "collect" for i in result["findings"])


def test_judgment_needs_independent_non_copied_support(reviewer):
    reviewer[1]["type"] = "comparison"
    a, b = evidence(), evidence(1, domain="other.example")
    c = claim()
    c["evidence_ids"] = [a.evidence_id, b.evidence_id]
    # Slightly changed boilerplate is still copied content.
    b.full_text = a.full_text
    result, _ = review([a, b], [c])
    assert result["verdict"] == "rework"
    b.full_text = "A separately researched buyer study explains monthly team charges and confirms twelve dollars per licensed seat."
    result, _ = review([a, b], [c])
    assert result["verdict"] == "pass"


def test_any_valid_claim_no_longer_covers_every_dimension():
    qr = audit.evaluate_quality(["Acme", "Other"], ["Pricing", "Features"], [claim()], [evidence()], {})
    assert qr.coverage_by_dimension == {"Pricing": False, "Features": False}
    assert sum(c["status"] == "missing" for c in qr.coverage_matrix) == 3


def test_custom_dimension_is_semantically_reviewed(reviewer):
    reviewer[1]["transform"] = lambda u: "unsupported" if u["kind"] == "coverage" else "supported"
    result, _ = review([evidence()], focus=["Procurement approval workflow"])
    assert any(i["kind"] == "coverage" and i["severity"] == "high" for i in result["findings"])


def test_structured_and_chart_assertions_are_all_reviewed(reviewer):
    structured = {"feature_tree": [{"brand": "Acme", "modules": [{"name": "Editor", "sub_features": [
        {"name": "Offline", "support": "full", "evidence_ids": ["e_0"]}]}]}],
        "pricing_model": [{"brand": "Acme", "currency": "USD", "model_type": "subscription", "tiers": [
            {"name": "Pro", "price": 12, "evidence_ids": ["e_0"]}]}],
        "user_persona": [{"brand": "Acme", "personas": [{"name": "Editor", "evidence_ids": ["e_0"]}]}]}
    analysis = {"comparison": {"dimensions": ["Depth"], "scores": [{"brand": "Acme", "values": [80], "evidence_ids": ["e_0"]}]},
                "market_share": [{"name": "Acme", "value": 20, "evidence_ids": ["e_0"]}],
                "trends": {"x": ["2026"], "series": [{"values": [1]}], "evidence_ids": ["e_0"]}}
    review([evidence()], structured=structured, analysis=analysis)
    kinds = {u["kind"] for p in reviewer[0] for u in p["items"]}
    assert {"claim", "feature", "pricing", "persona", "chart", "coverage"} <= kinds


def test_all_claims_and_cited_fragments_reach_reviewer(reviewer):
    claims = [{**claim(text=f"Pricing fact {i}"), "claim_id": f"c_{i}"} for i in range(37)]
    review([evidence(text="Actual long pricing terms. " * 180)], claims)
    units = [u for p in reviewer[0] for u in p["items"] if u["kind"] == "claim"]
    assert len(units) == 37
    assert all(len(u["sources"][0]["text"]) > 280 for u in units)
    assert len(reviewer[0]) > 1


@pytest.mark.parametrize("failure", [TimeoutError("timeout"), RuntimeError("quota"), None, {}, {"checks": []}])
def test_unavailable_or_incomplete_review_never_falls_back(monkeypatch, reviewer, failure):
    def broken(*args, **kwargs):
        if isinstance(failure, Exception):
            raise failure
        return failure
    monkeypatch.setattr(llm, "chat_json", broken)
    with pytest.raises(audit.AuditUnavailable):
        review([evidence()])


def test_unknown_requires_targeted_success_and_is_reviewed(reviewer):
    unknown = {"brand": "Acme", "dimension": "Pricing", "reason": "No published price found.", "search_ids": ["s_1"], "evidence_ids": []}
    history = [{"search_id": "s_1", "query": "Acme Pricing original terms", "brand": "Acme", "dimension": "Pricing",
                "status": "success", "result_count": 0}]
    reviewer[1]["transform"] = lambda u: "unknown" if u["kind"] in ("unknown", "coverage") else "supported"
    result, qr = review([evidence()], claims=[], analysis={"unknowns": [unknown]}, searches=history)
    assert result["verdict"] == "pass" and qr.coverage_matrix[0]["status"] == "unknown"
    history[0]["status"] = "error"
    result, _ = review([evidence()], claims=[], analysis={"unknowns": [unknown]}, searches=history)
    assert result["verdict"] == "rework"
    history[0].update(status="success", result_count=4, usable_count=0)
    assert not audit.valid_unknown(unknown, history, {"e_0": evidence().to_dict()})


def test_reviewer_cannot_declare_unknown_without_provenance(reviewer):
    reviewer[1]["status"] = "unknown"
    result, _ = review([evidence()])
    assert result["verdict"] == "rework"


def test_invalid_citation_survives_coercion_as_audit_finding(reviewer):
    result, _ = review([evidence()], structured={"citation_errors": [{"value": "bad e_fake"}]})
    assert result["verdict"] == "rework"


def test_unknown_cannot_be_used_as_price_and_shares_are_not_normalized():
    u = {"brand": "Acme", "dimension": "Pricing", "reason": "Not public", "evidence_ids": ["e_0"]}
    analysis = {"unknowns": [u], "pricing": [{"brand": "Acme", "entry_price": 12, "evidence_ids": ["e_0"]}],
                "market_share": [{"name": "Acme", "value": 130, "evidence_ids": ["e_0"]}]}
    qr = audit.evaluate_quality(["Acme"], ["Pricing"], [], [evidence()], {}, analysis=analysis)
    assert sum(i["kind"] == "numeric" for i in qr.issues) == 2
    assert pipeline._sanitize_share(analysis["market_share"])[0]["value"] == 130


def test_scores_do_not_count_as_resolutions_or_close_deleted_core_answers():
    old = audit.issue("claim", "Unsupported price", brand="Acme", dimension="Pricing")
    assert audit.track_issues([old], [], {"scores": {"Evidence": 100}})[0]["status"] == "still_open"
    gap = audit.issue("coverage", "Missing pricing", brand="Acme", dimension="Pricing", kind="coverage")
    resolutions = [{"issue_id": old["issue_id"], "status": "removed", "reason": "Removed the assertion"}]
    tracked = audit.track_issues([old], [gap], {"resolutions": resolutions})
    assert tracked[0]["status"] == "still_open" and tracked[1]["status"] == "new"


def test_evidence_packets_include_new_and_old_material_without_28_item_cutoff():
    evs = [evidence(i, brand="Acme" if i % 2 else "Other", text=f"Source {i} " + "a" * 1400) for i in range(40)]
    packets = evidence_batches(evs, priority_ids=["e_39"])
    assert {e.evidence_id for p in packets for e in p} == {e.evidence_id for e in evs}
    assert "e_39" in [e.evidence_id for e in packets[0]]
    assert len(packets) > 1


def test_batch_numeric_conflicts_are_not_silently_overwritten():
    merged = merge_analysis([{"pricing": [{"brand": "Acme", "entry_price": 12}]},
                             {"pricing": [{"brand": "Acme", "entry_price": 30}]}])
    assert merged["analysis_conflicts"]


def test_sibling_subdomains_do_not_count_as_independent_owners():
    a = evidence(domain="docs.acme.example", text="Acme pricing plans cost twelve dollars per month.")
    b = evidence(1, domain="news.acme.example", text="Corporate news announces a subscription offering for business users.")
    assert audit.independent_sources(["e_0", "e_1"], {e.evidence_id: e.to_dict() for e in [a, b]}) == 1


def test_rule_disappearance_needs_no_score_based_inference_but_cannot_hide_a_core_gap():
    old = {**audit.issue("old-item", "Invalid citation", brand="Acme", dimension="Pricing"), "origin": "rule"}
    tracked = audit.track_issues([old], [], {"checks": []})
    assert tracked[0]["status"] == "removed"
    gap = audit.issue("coverage", "Missing price", brand="Acme", dimension="Pricing", kind="coverage")
    assert audit.track_issues([old], [gap], {"checks": []})[0]["status"] == "still_open"


def test_a_still_present_assertion_cannot_be_reported_as_removed():
    old = audit.issue("item", "Unsupported assertion")
    result = audit.track_issues([old], [], {
        "checks": [{"item_id": "item", "status": "supported"}],
        "resolutions": [{"issue_id": old["issue_id"], "status": "removed", "reason": "Removed it"}]})
    assert result[0]["status"] == "still_open"


def test_mixed_brand_sentiment_is_detected_without_changing_classification_algorithm():
    qr = audit.evaluate_quality(["Acme", "Other"], ["User sentiment"], [], [evidence()], {}, sentiment={
        "sample_size": 2, "overall_count": {"pos": 1, "neg": 1, "neu": 0},
        "classification_target": "Acme", "sample_brands": ["Acme", "Other"]})
    assert any(i["kind"] == "sentiment" and i["severity"] == "high" for i in qr.issues)


def test_search_log_distinguishes_empty_results_and_service_errors(monkeypatch):
    from app.core import search
    def run(query, **kwargs):
        if "broken" in query:
            raise search.SearchUnavailable("quota exhausted")
        return []
    monkeypatch.setattr(search, "search", run)
    history = []
    assert search.multi_search(["Acme pricing", "broken service"], query_log=history) == []
    assert history[0]["status"] == "success" and history[0]["result_count"] == 0
    assert history[1]["status"] == "error" and "quota" in history[1]["error"]


def test_collection_records_per_query_outcomes_and_content_kind(offline, monkeypatch):
    def search(queries, **kwargs):
        kwargs["query_log"].extend([
            {"search_id": "s1", "query": queries[0], "status": "success", "result_count": 1},
            {"search_id": "s2", "query": queries[1], "status": "success", "result_count": 1}])
        return [{"url": "https://acme.example/pricing", "query": queries[0], "title": "Acme", "snippet": "Acme published pricing"}]
    monkeypatch.setattr(pipeline, "multi_search", search)
    monkeypatch.setattr(pipeline, "fetch_page", lambda *a, **k: {"ok": True, "degraded": True, "text": "Acme snippet only"})
    history = []
    result = pipeline._collect_brand("Acme", ["Pricing terms", "Feature docs"], "collector", 6, "year", set(), "",
                                     history, {"Acme Pricing terms": "Pricing", "Acme Feature docs": "Features"})
    assert result["evidences"][0].content_kind == "snippet"
    assert history[0]["usable_count"] == 1 and history[1]["usable_count"] == 0
    assert history[0]["dimension"] == "Pricing"


def test_evidenced_unknown_can_close_a_missing_dimension():
    old = {**audit.issue("coverage_item", "Missing price", brand="Acme", dimension="Pricing", kind="coverage"), "origin": "rule"}
    tracked = audit.track_issues([old], [], {"checks": [
        {"item_id": "coverage_item", "kind": "coverage", "status": "unknown"}]})
    assert tracked[0]["status"] == "declared_unknown"


def test_unknown_only_analysis_does_not_discard_its_provenance(offline, monkeypatch):
    u = {"brand": "Acme", "dimension": "Pricing", "reason": "Not disclosed", "search_ids": ["s1"], "evidence_ids": []}
    monkeypatch.setattr(pipeline, "chat_json", lambda *a, **k: {"claims": [], "unknowns": [u]})
    result = pipeline._analyze("Acme price", ["Acme"], ["Pricing"], [evidence()], ["L2-002"])
    assert result["claims"] == [] and result["unknowns"] == [u]


def test_claims_cannot_cite_sources_not_seen_in_their_analysis_packet(offline, monkeypatch):
    def analyze(messages, **kwargs):
        sent = kwargs["mock_context"]["evidence"]
        return {"claims": [{"text": "Claim from this packet", "field": "pricing_model",
                            "evidence_ids": [sent[0]["evidence_id"], "e_never_sent"], "author": "L2-002"}]}
    monkeypatch.setattr(pipeline, "chat_json", analyze)
    result = pipeline._analyze("Acme", ["Acme"], ["Pricing"], [evidence()], ["L2-002"])
    assert result["claims"][0]["evidence_ids"] == ["e_0"]
    assert result["citation_errors"]


def test_an_actual_quote_can_use_a_single_comment_source(reviewer):
    reviewer[1].update(type="quote", official=False)
    e = evidence()
    e.source_type, e.content_kind = "reddit", "comment"
    result, _ = review([e])
    assert result["verdict"] == "pass"


def test_repeated_packet_targets_are_reviewed_together_with_all_citations(reviewer):
    a, b = evidence(), evidence(1)
    structured = {"feature_tree": [{"brand": "Acme", "modules": [
        {"name": "Editor", "sub_features": [{"name": "Offline", "support": "full", "evidence_ids": ["e_0"]}]},
        {"name": "Editor", "sub_features": [{"name": "Offline", "support": "none", "evidence_ids": ["e_1"]}]},
    ]}]}
    review([a, b], structured=structured)
    units = [u for p in reviewer[0] for u in p["items"] if u["kind"] == "feature"]
    assert len(units) == 1
    assert set(units[0]["evidence_ids"]) == {"e_0", "e_1"}
    assert "variants" in json.loads(units[0]["value"])
