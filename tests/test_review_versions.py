"""Evidence support, date/pricing comparability and dependency-local invalidation."""
import copy
import pytest
from app.core import db, versions
from app.core.models import ReportContent, ReportItem
from app.core.review import apply_reviews, citation_problem, charts

@pytest.fixture
def content(scope):
    c = ReportContent(products=scope["products"], topics=scope["topics"], checked_at="2026-10-10T12:00:00Z", changes_since="2026-07-12").model_dump()
    c["evidence"] = [
        {"evidence_id": "ev1", "product_id": "notion", "topic_id": "features", "source_url": "https://www.notion.com/pricing", "source_type": "official",
         "title": "Notion plans", "excerpt": "Notion Pro costs USD 10 per seat per month, billed monthly.", "context": "Notion Pro costs USD 10 per seat per month, billed monthly. Released on 2026-09-01.", "captured_at": "2026-10-10T12:00:00Z", "published_at": "2026-09-01"},
        {"evidence_id": "ev2", "product_id": "obsidian", "topic_id": "features", "source_url": "https://obsidian.md/pricing", "source_type": "official",
         "title": "Obsidian plans", "excerpt": "Obsidian Pro costs USD 10 per seat per month, billed monthly.", "context": "Obsidian Pro costs USD 10 per seat per month, billed monthly.", "captured_at": "2026-10-10T12:00:00Z", "published_at": None},
    ]
    for i, p in enumerate(scope["products"], 1):
        c["comparison"].append(ReportItem(id="fact" + str(i), product_id=p["id"], topic_id="features",
            text=p["name"] + " Pro costs USD 10 per seat per month, billed monthly.",
            citations=[{"evidence_id": "ev" + str(i), "quote": c["evidence"][i-1]["excerpt"]}]).model_dump())
    return c

def response(items, status="supported", reason="The quoted source directly supports this statement under these conditions."):
    return {"reviews": [{"item_id": i["id"], "status": status, "reason": reason, "evidence_ids": [r["evidence_id"] for r in i["citations"]], "quotes": i["citations"]} for i in items]}

def test_one_applicable_official_source_can_support_fact(content):
    apply_reviews(content, content["comparison"], response(content["comparison"]))
    assert all(i["review"]["status"] == "supported" for i in content["comparison"])
    assert content["review_summary"]["counts"]["supported"] == 2
    assert "score" not in content["review_summary"]

@pytest.mark.parametrize("fault", ["missing", "wrong_product", "unlocatable", "no_sources"])
def test_citation_validity_is_separate_from_support(content, fault):
    item = content["comparison"][0]
    if fault == "missing":
        item["citations"][0]["evidence_id"] = "invented"
    elif fault == "wrong_product":
        item["citations"][0]["evidence_id"] = "ev2"
    elif fault == "unlocatable":
        item["citations"][0]["quote"] = "This product is free forever."
    else:
        item["citations"] = []
    apply_reviews(content, [item], response([item]))
    assert item["review"]["status"] == "unknown"
    assert item["review"]["citation_valid"] is False
    assert item["review"]["support_checked"] is False

def test_existing_citation_does_not_prove_compound_claim(content):
    item = content["comparison"][0]
    item["text"] += " It also has unlimited free enterprise support."
    apply_reviews(content, [item], response([item], "unknown", "This quotation supports price only; it does not establish unlimited enterprise support."))
    assert item["review"]["citation_valid"] is True
    assert item["review"]["status"] == "unknown"

def test_multiple_domains_do_not_auto_pass(content):
    item = content["comparison"][0]
    external = {**content["evidence"][0], "evidence_id": "external", "source_url": "https://review.test/notion", "source_type": "external"}
    content["evidence"].append(external)
    item["citations"].append({"evidence_id": "external", "quote": external["excerpt"]})
    apply_reviews(content, [item], None)
    assert item["review"]["status"] == "pending_review"

def test_reviewer_memory_cannot_reject_a_supported_source(content):
    item = content["comparison"][0]
    bad = {"reviews": [{"item_id": item["id"], "status": "conflicting", "reason": "I remember a different price.", "evidence_ids": ["ev1"], "quotes": []}]}
    apply_reviews(content, [item], bad)
    assert item["review"]["status"] == "pending_review"
    assert not item["review"]["support_checked"]

def test_conflict_requires_two_locatable_applicable_sources(content):
    item = content["comparison"][0]
    other = {**content["evidence"][0], "evidence_id": "other", "context": "Notion Pro costs USD 12 per seat per month, billed monthly.", "excerpt": "Notion Pro costs USD 12 per seat per month, billed monthly."}
    content["evidence"].append(other)
    item["citations"].append({"evidence_id": "other", "quote": other["excerpt"]})
    apply_reviews(content, [item], response([item], "conflicting", "Applicable monthly prices contradict; no effective-date explanation was found."))
    assert item["review"]["status"] == "conflicting"

def test_missing_or_duplicate_review_stays_pending(content):
    item = content["comparison"][0]
    record = response([item])["reviews"][0]
    apply_reviews(content, [item], {"reviews": [record, record]})
    assert item["review"]["status"] == "pending_review"

@pytest.mark.parametrize("date", [None, "2026-01-01", "2026-12-01", "not-a-date"])
def test_changes_require_real_dates_in_window(content, date):
    item = content["comparison"][0]
    item.update(kind="change", effective_date=date)
    assert citation_problem(item, content)
    apply_reviews(content, [item], response([item]))
    assert item["review"]["status"] != "supported"

def test_release_date_not_capture_date(content):
    item = content["comparison"][0]
    item.update(kind="change", effective_date="2026-09-01")
    item["citations"][0]["quote"] = "Released on 2026-09-01."
    assert not citation_problem(item, content)
    assert content["evidence"][0]["captured_at"].startswith("2026-10-10")

def test_price_chart_requires_conditions_and_support(content):
    for item in content["comparison"]:
        item["conditions"] = {"value": 10, "plan": "Pro", "currency": "USD", "billing_period": "monthly", "seats": 1, "unit": "seat/month"}
    assert charts(content) == []
    apply_reviews(content, content["comparison"], response(content["comparison"]))
    assert len(content["charts"]) == 1
    assert all(p["citations"] for p in content["charts"][0]["points"])
    content["comparison"][1]["conditions"]["billing_period"] = "annual"
    assert charts(content) == []
    content["comparison"][0]["conditions"].pop("currency")
    assert citation_problem(content["comparison"][0], content)

def test_manual_edit_invalidates_only_transitive_dependencies(offline, content):
    a, b = content["comparison"]
    content["brief"] = [ReportItem(id="judgment", kind="inference", text="A conditional judgment.", citations=a["citations"], depends_on=[a["id"]]).model_dump(),
                        ReportItem(id="dependent", kind="inference", text="A dependent conclusion.", citations=a["citations"], depends_on=["judgment"]).model_dump()]
    apply_reviews(content, content["comparison"] + content["brief"], response(content["comparison"] + content["brief"]))
    initial = db.create_version(None, content, "research")
    edited = versions.edit(initial["report_id"], initial["version_id"], {a["id"]: "Edited price"})
    result = {i["id"]: i for i in edited["content"]["comparison"] + edited["content"]["brief"]}
    assert result[a["id"]]["review"]["status"] == "pending_review"
    assert result["judgment"]["review"]["status"] == "pending_review"
    assert result["dependent"]["review"]["status"] == "pending_review"
    assert result[b["id"]]["review"] == b["review"]
    assert db.get_version(initial["report_id"], initial["version_id"])["content"] == content

def test_unresolved_dependencies_and_cycles_cannot_support_judgment(content):
    a = content["comparison"][0]
    content["brief"] = [ReportItem(id="judgment", kind="inference", text="A conclusion.", citations=a["citations"], depends_on=["missing"]).model_dump()]
    apply_reviews(content, content["comparison"] + content["brief"], response(content["comparison"] + content["brief"]))
    assert content["brief"][0]["review"]["status"] == "unknown"
    content["brief"][0]["depends_on"] = ["judgment"]
    apply_reviews(content, content["brief"], response(content["brief"]))
    assert content["brief"][0]["review"]["status"] == "pending_review"

def test_comparative_inference_can_quote_both_confirmed_products(content):
    facts = content["comparison"]
    judgment = ReportItem(id="comparison", kind="inference", text="Both quoted plans have the same monthly seat price.",
        citations=[r for i in facts for r in i["citations"]], depends_on=[i["id"] for i in facts]).model_dump()
    content["brief"] = [judgment]
    apply_reviews(content, facts + [judgment], response(facts + [judgment]))
    assert judgment["review"]["status"] == "supported"
    assert judgment["review"]["quotes"] == judgment["citations"]

def test_incomplete_billing_conditions_do_not_invalidate_a_real_quote(content):
    item = content["comparison"][0]
    item["conditions"] = {"value": 10, "currency": "USD"}
    apply_reviews(content, [item], response([item]))
    assert item["review"]["citation_valid"] is True
    assert item["review"]["status"] == "unknown"
    assert "billing conditions" in item["review"]["reason"]

@pytest.mark.parametrize("invalid", [None, {"reviews": None}, {"reviews": [{"item_id": "fact1", "status": "supported", "evidence_ids": [{}], "quotes": ["invalid"]}]}])
def test_malformed_reviewer_output_stays_pending(content, invalid):
    item = content["comparison"][0]
    apply_reviews(content, [item], invalid)
    assert item["review"]["status"] == "pending_review"

@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_chart_values_are_rejected(content, value):
    for item in content["comparison"]:
        item["conditions"] = {"value": value, "plan": "Pro", "currency": "USD", "billing_period": "monthly", "seats": 1, "unit": "seat/month"}
        item["review"]["status"] = "supported"
    assert charts(content) == []
