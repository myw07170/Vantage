"""Deterministic LLM substitute using explicit context and supplied sources.

Source excerpts are copied rather than interpreted. Missing commercial data
stays missing, and quality reviews retain the real rule-derived findings.
"""
from __future__ import annotations

import copy
import json
import re


def _evidence(context: dict) -> list[dict]:
    return [e for e in context.get("evidence", [])
            if isinstance(e, dict) and e.get("evidence_id") and e.get("excerpt")]


def _section(context: dict) -> dict:
    title = str(context.get("title") or "Research")
    evidence = _evidence(context)
    paragraphs = []
    for i in range(max(1, int(context.get("min_paragraphs", 3)))):
        prefix = f"[MOCK] {title}, source note {i + 1}. "
        if i < len(evidence):
            e = evidence[i]
            paragraphs.append(prefix + "The supplied source excerpt reads: "
                              + str(e["excerpt"]) + f" [{e['evidence_id']}]")
        else:
            paragraphs.append(
                prefix + "No additional evidence was supplied for this part of the "
                "section. This simulated draft cannot establish further conclusions, "
                "prices, market shares or recommendations. Collect and verify sources "
                "before using a real LLM to assess this question."
            )
    notes = context.get("annotations") or []
    if notes:
        paragraphs.append("[MOCK] Reader annotations received: " + "; ".join(str(n) for n in notes)
                          + ". The simulation records these requests without inferring new facts.")
    if context.get("fix_directive"):
        paragraphs.append("[MOCK] Verification rewrite requested. This draft uses only supplied "
                          "source excerpts; remaining mechanical findings must still be reviewed.")
    return {
        "paragraphs": paragraphs,
        "key_takeaway": f"[MOCK] {title}: simulated source notes, not an analytical conclusion.",
        "highlights": ["[MOCK] No model inference was performed.",
                       "[MOCK] Missing information remains a research gap."],
    }


def _result(kind: str, context: dict):
    if kind == "writing_notes":
        units = context["units"]
        return {"accounted_unit_ids": [u["unit_id"] for u in units], "notes": [
            {"text": "[MOCK] Supplied materials indexed; no model inference performed.",
             "evidence_ids": list(dict.fromkeys(i for u in units for i in u["evidence_ids"]))}]}
    if kind == "writing_plan_review":
        return {"verdict": "pass", "issues": [], "simulated": True}
    if kind == "writing_plan":
        # Development-only outline reflects supplied dimensions, never inferred facts.
        focus, units, assets = context["focus"], context["units"], context["assets"]
        eids = [u["unit_id"] for u in units if u["kind"] == "evidence"]
        cids = [u["unit_id"] for u in units if u["kind"] == "claim"]
        chapters = []
        allocation = max(1, context["target_words"] // (len(focus) + 1))
        for i, dim in enumerate(focus):
            components = []
            low = dim.lower()
            for key, asset in assets.items():
                if (("pric" in low and asset["kind"] == "pricing_model") or
                    ("feature" in low and asset["kind"] == "feature_tree") or
                    ("sentiment" in low and asset["kind"] == "sentiment")):
                    components.append({"kind": asset["kind"], "ref": key, "caption": ""})
            chapters.append({"id": f"question_{i + 1}", "title": dim, "role": "body",
                "goal": "[MOCK] Present supplied source notes for " + dim, "answers": [dim], "depends_on": [],
                "evidence_ids": eids, "claim_ids": cids, "data_refs": [], "components": components,
                "target_words": allocation, "author": context["members"][0]})
        chapters.insert(0, {"id": "summary", "title": "Research brief", "role": "summary",
            "goal": "[MOCK] Summarize the available source notes without analytical inference.",
            "answers": [], "depends_on": [c["id"] for c in chapters], "claim_ids": cids, "evidence_ids": eids,
            "data_refs": [], "components": [], "target_words": allocation, "author": context["members"][0]})
        used = set(eids + cids + [a["ref"] for c in chapters for a in c["components"]])
        return {"title": "[MOCK] " + context["query"], "purpose": context["query"],
            "thesis": "[MOCK] Source notes only; no model argument was generated.", "brands": context["brands"],
            "chapters": chapters, "unused_material": [{"id": u["unit_id"], "reason": "[MOCK] Not assigned in the simulated outline."}
                                                       for u in units if u["unit_id"] not in used]}
    if kind == "writing_edit":
        return copy.deepcopy(context["draft"])
    if kind == "writing_assertions":
        return {"accounted_blocks": [b["unit_id"] for b in context["blocks"]], "assertions": []}
    if kind == "writing_support":
        return {"checks": [{"unit_id": u["unit_id"], "status": "supported",
                            "reason": "[MOCK] Simulated support check.", "fix": "", "basis": "official_fact",
                            "supporting_evidence_ids": u["evidence_ids"]} for u in context["units"]]}
    if kind == "echo":
        return str(context.get("text", "ready"))
    if kind == "json":
        return copy.deepcopy(context.get("result", {}))
    if kind == "scope":
        # Explicit mock fixtures only; production recognition always calls the LLM.
        query = str(context.get("query", ""))
        fixtures = ("Claude Code", "Codex", "Notion", "Obsidian", "Craft")
        products = [name for name in fixtures if re.search(r"\b" + re.escape(name) + r"\b", query, re.I)]
        notes = [h["explanation"] for h in context.get("history", [])]
        brief = query + ((". User corrections: " + "; ".join(notes)) if notes else "")
        return {"subject": query, "domain": "", "research_brief": brief,
                "products": products, "competitors": []}
    if kind == "plan":
        brands = list(dict.fromkeys(str(b).strip() for b in context.get("brands", []) if str(b).strip()))
        subject = brands[0] if brands else str(context.get("query", "")).strip()
        return {
            "subject": subject, "category": "", "brands": brands,
            "focus": context.get("focus") or ["Feature comparison", "Pricing strategy", "User sentiment"],
            "search_angles": ["product features", "pricing plans", "user reviews", "latest news",
                              "documentation", "release notes", "customer support", "integrations", "security"]
                             [:context.get("max_angles", 7)],
        }
    if kind == "clarify":
        # Mock does not invent preferences or pretend to understand user intent.
        return {"status": "ready", "context": {}}
    if kind == "dispatch":
        scores = context.get("scores", {})
        candidates = sorted(context.get("candidates", []),
                            key=lambda e: (-scores.get(e["id"], 0), e["id"]))
        picked = [e for e in candidates if e["level"] == "L2"][:context.get("min_strategy", 2)]
        return {"members": [{"id": e["id"], "reason": "[MOCK] " + e.get("work_instructions", {}).get("responsibilities", ["Matched to research priorities."])[0]}
                            for e in picked]}
    if kind == "analyze":
        authors = context.get("authors") or ["L2-001"]
        return {
            "claims": [{"text": "[MOCK] Supplied source excerpt: " + str(e["excerpt"]),
                        "field": "overview", "evidence_ids": [e["evidence_id"]],
                        "author": authors[i % len(authors)]}
                       for i, e in enumerate(_evidence(context))],
            "comparison": {"dimensions": [], "scores": []}, "pricing": [],
            "market_share": [], "five_forces": {}, "trends": {},
        }
    if kind == "structured":
        # Index supplied titles, not inferred product capabilities or prices.
        return {
            "feature_tree": [{"brand": brand, "modules": [
                {"category": "[MOCK] Evidence index", "name": str(e.get("title") or "Source"),
                 "sub_features": []}
                for e in _evidence(context) if e.get("brand") == brand
            ]} for brand in context.get("brands", [])],
            "pricing_model": [], "user_persona": [],
        }
    if kind == "sentiment":
        from app.core.sentiment import _rule_sentiment
        return [{"i": i, "s": _rule_sentiment(str(c.get("text", "")))}
                for i, c in enumerate(context.get("comments", []))]
    if kind == "quotes":
        return [{"i": i, "phrase": str(c.get("text", ""))[:89]}
                for i, c in enumerate(context.get("comments", [])[:6]) if c.get("text")]
    if kind in ("quality_review", "report_review"):
        review = copy.deepcopy(context["rule_review"])
        if kind == "report_review":
            review["review"] = (
                "[MOCK] This verdict rests on the automated checks alone. No model "
                "review of cross-section consistency or factual support was performed."
            )
        else:
            review["review"] = "[MOCK] No model review performed. " + str(review.get("review", ""))
        return review
    if kind in ("write_section", "refine_section"):
        return _section(context)
    if kind == "sentiment_narrative":
        sentiment = context.get("sentiment", {})
        return {
            "paragraphs": [
                f"[MOCK] The collection contains {sentiment.get('sample_size', 0)} linked comments. "
                "Sentiment labels use deterministic keyword rules and are not a model judgement.",
                "[MOCK] The simulated narrative makes no inference about audience composition "
                "or competitive preference. Review the linked comments before drawing conclusions.",
            ],
            "key_takeaway": "[MOCK] Comment collection is available; model interpretation is absent.",
            "highlights": [],
        }
    if kind:
        raise ValueError(f"Unknown mock task_kind: {kind}")
    return {}


def complete(messages: list[dict], task_kind: str, context: dict, json_mode: bool) -> str:
    result = _result(task_kind, context)
    if json_mode:
        if isinstance(result, list):
            result = {"items": result}
        elif isinstance(result, str):
            result = {"text": result}
        return json.dumps(result, ensure_ascii=False)
    if isinstance(result, str):
        return result
    if isinstance(result, dict) and "paragraphs" in result:
        return "\n\n".join(result["paragraphs"])
    return "[MOCK] No model inference performed."
