"""Demand-driven planning, complete material use and independent written checks."""
import copy
import json

import pytest

from app.core import llm, llm_mock, orchestrator as pipeline, writing as w
from app.core.models import Evidence
from app.core.verify import Finding, VerifyReport, verdict_of
from app.core.written_review import review_document


def sources(count=1, long=False):
    return [Evidence(f"e_{i:08x}", f"https://acme-{i}.example/terms", "official", f"Acme terms {i}",
                     "Acme costs USD 12 monthly.", "2026-10-14", 80, "collector", brand="Acme",
                     full_text=("Acme published conditions. " * 130 if long else "") + f"END_{i} Acme costs USD 12 monthly.", content_kind="body")
            for i in range(count)]


def claims(evs):
    return [{"claim_id": f"c_{i}", "text": f"Published source {i} describes Acme terms.", "field": "pricing_model",
             "evidence_ids": [e.evidence_id], "confidence": "low", "author": "L2-002"} for i, e in enumerate(evs)]


def mock_complete(messages, *, task_kind, mock_context=None, **kwargs):
    return llm_mock._result(task_kind, mock_context or {})


def plan(evs=None, dims=None, query="Select Acme for a small team", complete=mock_complete):
    evs = evs or sources()
    return w.plan_report(query, ["Acme"], dims or ["Pricing"], {}, ["L2-002"], "quick", evs,
                         claims(evs), {}, {}, "Use American English. ", "test", complete)


def test_outline_changes_with_user_needs_and_has_no_forced_frameworks():
    a, b = plan(dims=["Budget constraints"]), plan(dims=["Offline workflow", "Migration risk"])
    assert [c["title"] for c in a["chapters"]] != [c["title"] for c in b["chapters"]]
    assert not {"swot", "moat", "sentiment", "overview"} & {c["id"] for c in b["chapters"]}
    assert b["planning_review"]["verdict"] == "pass"


def test_invalid_planning_is_corrected_once_and_never_falls_back():
    attempts = []
    def complete(messages, **kw):
        if kw["task_kind"] == "writing_plan":
            attempts.append(json.loads(messages[-1]["content"]))
            return {"title": "Invalid", "brands": ["Wrong product"], "chapters": []}
        return mock_complete(messages, **kw)
    with pytest.raises(w.WritingError, match="after correction"):
        plan(complete=complete)
    assert len(attempts) == 2 and "changed the confirmed products" in attempts[1]["correction_required"]


def test_semantically_wrong_outline_is_rejected_even_with_answer_labels():
    count = []
    def complete(messages, **kw):
        if kw["task_kind"] == "writing_plan_review":
            count.append(1)
            return {"verdict": "revise", "issues": ["The goals do not answer the user's budget decision."]}
        return mock_complete(messages, **kw)
    with pytest.raises(w.WritingError, match="Outline review"):
        plan(complete=complete)
    assert len(count) == 2


def test_dependencies_order_actual_body_before_summary_and_detect_cycles():
    chapters = [{"id": "summary", "depends_on": ["decision"]}, {"id": "facts", "depends_on": []},
                {"id": "risk", "depends_on": []}, {"id": "decision", "depends_on": ["facts", "risk"]}]
    assert w.dependency_groups(chapters) == [["facts", "risk"], ["decision"], ["summary"]]
    chapters[1]["depends_on"] = ["summary"]
    with pytest.raises(w.WritingError, match="cycle"):
        w.dependency_groups(chapters)


def test_all_material_is_indexed_and_assigned_without_old_caps():
    evs = sources(40, long=True)
    seen = []
    def complete(messages, **kw):
        if kw["task_kind"] == "writing_notes":
            seen.extend(kw["mock_context"]["units"])
        return mock_complete(messages, **kw)
    result = plan(evs=evs, complete=complete)
    assert {e.evidence_id for e in evs} <= {u["unit_id"].split(":")[0] for u in seen}
    assert any("END_39" in u["value"] for u in seen)
    assert len(result["material_usage"]) == 80
    assert len(result["chapters"][0]["evidence_ids"]) == 40


def test_material_indexing_failure_does_not_silently_drop_units():
    def incomplete(*args, **kw):
        return {"accounted_unit_ids": [], "notes": [{"text": "missing", "evidence_ids": []}]}
    with pytest.raises(w.WritingError, match="every input"):
        plan(complete=incomplete)


def test_user_length_overrides_mode_and_short_material_has_no_paragraph_floor():
    assert w.target_words("Write 2,200 words", {}, "quick") == 2200
    assert [w.target_words("Compare Acme", {}, m) for m in ("quick", "deep", "expert")] == [1500, 4000, 8000]
    assert w.normalize_draft({"paragraphs": ["One adequate sourced paragraph."], "key_takeaway": "A short answer."})["paragraphs"]


def test_writer_reads_predecessor_actual_content_and_preserves_retry_constraints():
    evs = sources()
    p = plan(evs=evs)
    summary = p["chapters"][0]
    completed = {c["id"]: {"paragraphs": ["Actual revised predecessor outcome."], "key_takeaway": "The actual outcome.",
                 "source_evidence_ids": [evs[0].evidence_id]} for c in p["chapters"] if c["role"] == "body"}
    calls = []
    def complete(messages, **kw):
        calls.append((kw["task_kind"], messages))
        if kw["task_kind"] == "write_section" and sum(k == "write_section" for k, _ in calls) == 1:
            return None
        return mock_complete(messages, **kw)
    result = w.write_chapter(summary, p, "Budget decision", ["Acme"], ["Pricing"], evs, claims(evs),
                              {"unknowns": [{"brand": "Acme", "dimension": "Revenue", "reason": "Not disclosed"}]},
                              {}, completed, "Research policy", "test", 3500, complete,
                              fix="Do not assume annual billing", previous="Prior draft.")
    prompts = [str(msg) for kind, msg in calls if kind == "write_section"]
    assert len(prompts) == 2
    assert all("Not disclosed" in msg and "Do not assume annual billing" in msg for msg in prompts)
    assert any("Actual revised predecessor outcome" in str(msg) for _, msg in calls)
    assert result["paragraphs"] and all(u["read_by"] for u in p["material_usage"])


def test_writer_cannot_fabricate_citations_on_retry():
    p, evs = plan(), sources()
    c = p["chapters"][1]
    def bad(messages, **kw):
        if kw["task_kind"] == "write_section":
            return {"paragraphs": ["Fabricated assertion [e_ffffffff]."], "key_takeaway": "bad"}
        return mock_complete(messages, **kw)
    with pytest.raises(w.WritingError, match="outside its supplied"):
        w.write_chapter(c, p, "Acme", ["Acme"], ["Pricing"], evs, claims(evs), {}, {}, {}, "", "test", 3500, bad)


def test_late_continuation_failure_retains_completed_parts_and_same_constraints():
    p, evs = plan(), sources()
    chapter = p["chapters"][1]
    chapter["target_words"] = 600
    calls = []
    def failing(messages, **kw):
        if kw["task_kind"] == "write_section":
            data = json.loads(messages[-1]["content"])
            calls.append(data)
            if data["part"] == 2:
                return None
        return mock_complete(messages, **kw)
    with pytest.raises(w.WritingError) as caught:
        w.write_chapter(chapter, p, "Acme", ["Acme"], ["Pricing"], evs, claims(evs), {}, {}, {}, "", "test", 400, failing,
                        fix="Retain published monthly terms")
    partial = caught.value.drafts[chapter["id"]]
    assert partial["paragraphs"] and len(calls) == 3
    assert all(c["required_fixes"] == "Retain published monthly terms" for c in calls)
    assert calls[-1]["completed_parts"]["paragraphs"] == partial["paragraphs"]


def test_editorial_failure_retains_completed_chapter_and_original_remaining_drafts():
    p, evs = plan(), sources()
    drafts = {c["id"]: {"paragraphs": ["Initial argument [e_00000000]."]} for c in p["chapters"]}
    calls = []
    def editor(messages, **kw):
        if kw["task_kind"] == "writing_edit":
            calls.append(1)
            if len(calls) > 1:
                raise RuntimeError("Provider unavailable")
            return {"paragraphs": ["Integrated argument [e_00000000]."]}
        return mock_complete(messages, **kw)
    with pytest.raises(w.WritingError) as caught:
        w.edit_report(p, drafts, "Choose Acme", claims(evs), {}, "", "test", editor)
    assert caught.value.drafts["summary"]["paragraphs"] == ["Integrated argument [e_00000000]."]
    assert caught.value.drafts["question_1"]["paragraphs"] == drafts["question_1"]["paragraphs"]


def verifier(status="supported", *, contradiction=False, basis="official_fact", inspect=None):
    def complete(messages, **kw):
        if inspect is not None:
            inspect.append((kw["task_kind"], messages))
        payload = json.loads(messages[-1]["content"])
        if kw["task_kind"] == "writing_assertions":
            rows = []
            for b in payload["blocks"]:
                if "UNREVIEWED_TAIL" in b["value"] or "WRONG_NUMBER" in b["value"]:
                    rows.append({"block_id": b["unit_id"], "quote": b["value"], "text": b["value"],
                                 "kind": "fact", "premise_claim_ids": [], "evidence_ids": b["evidence_ids"],
                                 "conditions": "", "topic": "price"})
            return {"accounted_blocks": [b["unit_id"] for b in payload["blocks"]], "assertions": rows}
        if kw["task_kind"] == "writing_support":
            return {"checks": [{"unit_id": u["unit_id"], "status": status, "reason": "Original terms checked.",
                                "fix": "Use the supported figure.", "basis": basis,
                                "supporting_evidence_ids": u["evidence_ids"]} for u in payload["units"]]}
        if kw["task_kind"] == "report_review" and contradiction:
            return {"verdict": "revise", "scores": {}, "review": "Chapters disagree.", "findings": [
                {"section_id": "decision", "severity": "major", "kind": "contradiction", "detail": "The decision contradicts the source chapter.", "fix": "Align them."}]}
        return mock_complete(messages, **kw)
    return complete


def document_review(complete, draft=None, plan_data=None):
    evs = sources()
    sections = draft or {"decision": {"key_takeaway": "Check the terms.", "paragraphs": [
        "Background. " * 120 + "UNREVIEWED_TAIL costs USD 99 [e_00000000]."], "highlights": []}}
    return review_document("Choose Acme", ["Acme"], sections, {sid: sid for sid in sections}, list(sections),
                           claims(evs), VerifyReport(), "test", "", plan_data or {"chapters": []},
                           [e.to_dict() for e in evs], {}, complete)


def test_written_tail_beyond_700_characters_is_independently_extracted_and_checked():
    calls = []
    result = document_review(verifier("unsupported", inspect=calls))
    assert result["assertions"] and any("UNREVIEWED_TAIL" in a["quote"] for a in result["assertions"])
    assert result["findings"][0]["severity"] == "major"
    assert any(kind == "writing_support" for kind, _ in calls)


def test_new_supported_facts_are_checked_not_rejected_merely_for_being_new():
    result = document_review(verifier("supported"))
    assert result["assertions"][0]["is_new"]
    assert result["verdict"] == "pass" and not result["findings"]


def test_captions_takeaways_and_highlights_are_checked_not_only_paragraphs():
    result = document_review(verifier("unsupported"), {
        "decision": {"paragraphs": ["Background."], "key_takeaway": "WRONG_NUMBER 99 [e_00000000].",
                     "highlights": ["WRONG_NUMBER 98 [e_00000000]."]}},
        {"chapters": [{"id": "decision", "components": [{"caption": "WRONG_NUMBER 97 [e_00000000]."}]}]})
    assert len(result["assertions"]) == 3
    assert len(result["findings"]) == 3


def test_global_check_catches_cross_chapter_disagreement():
    assert any(f["kind"] == "contradiction" for f in document_review(verifier(contradiction=True))["findings"])


def test_malformed_assertion_review_never_approves_a_report():
    def bad(messages, **kw):
        if kw["task_kind"] == "writing_assertions":
            return {"accounted_blocks": [], "assertions": []}
        return mock_complete(messages, **kw)
    with pytest.raises(w.WritingError, match="every block"):
        document_review(bad)


def test_editorial_new_numbers_are_checked_from_actual_edited_text():
    p, evs = plan(), sources()
    drafts = {c["id"]: {"paragraphs": ["The terms are available [e_00000000]."], "key_takeaway": "Read the terms."} for c in p["chapters"]}
    def editor(messages, **kw):
        if kw["task_kind"] == "writing_edit":
            return {"paragraphs": ["WRONG_NUMBER price is 999 [e_00000000]."], "key_takeaway": "Read the terms."}
        return mock_complete(messages, **kw)
    edited = w.edit_report(p, drafts, "Choose Acme", claims(evs), {}, "", "test", editor)
    result = document_review(verifier("unsupported"), edited, p)
    assert len(result["findings"]) == len(drafts)


@pytest.mark.parametrize("kind,basis,premises,accepted", [
    ("inference", "deduction", ["c_0"], True),
    ("recommendation", "recommendation", ["c_0"], True),
    ("inference", "official_fact", [], False),
    ("fact", "corroborated", [], False),  # one source cannot corroborate a comparison
    ("recommendation", "recommendation", [], False),
])
def test_new_judgments_require_their_actual_kind_and_verified_premises(kind, basis, premises, accepted):
    delegate = verifier("supported", basis=basis)
    def complete(messages, **kw):
        result = delegate(messages, **kw)
        if kw["task_kind"] == "writing_assertions":
            for row in result["assertions"]:
                row.update(kind=kind, premise_claim_ids=premises, conditions="For the evaluated monthly plan")
        return result
    result = document_review(complete)
    assert (not result["findings"]) is accepted


def test_unknowns_cannot_be_relabelled_as_recommendation_evidence():
    delegate = verifier("supported", basis="unknown")
    def complete(messages, **kw):
        result = delegate(messages, **kw)
        if kw["task_kind"] == "writing_assertions":
            for row in result["assertions"]:
                row.update(kind="recommendation", text="Unknown revenue means Acme should rank first.")
        if kw["task_kind"] == "writing_support":
            for row in result["checks"]:
                row["unknown_ref"] = {"brand": "Acme", "dimension": "Revenue"}
        return result
    evs = sources()
    result = review_document("Choose Acme", ["Acme"], {"decision": {"paragraphs": ["UNREVIEWED_TAIL Unknown revenue [e_00000000]."]}},
        {"decision": "Choose"}, ["decision"], claims(evs), VerifyReport(), "test", "", {"chapters": []},
        [e.to_dict() for e in evs], {"unknowns": [{"brand": "Acme", "dimension": "Revenue"}]}, complete)
    assert result["findings"][0]["severity"] == "major"


def test_remaining_minor_issues_are_flagged_rather_than_labelled_corrected():
    vr = VerifyReport()
    vr.add(Finding("purchase", "minor", "vague", "Clarify the applicability condition."))
    assert verdict_of(vr, {}) == "flagged"
