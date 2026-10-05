"""Deterministic LLM substitute using explicit context and supplied sources.

Source excerpts are copied rather than interpreted. Missing commercial data
stays missing, and quality reviews retain the real rule-derived findings.
"""
from __future__ import annotations

import copy
import json


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
    if kind == "echo":
        return str(context.get("text", "ready"))
    if kind == "json":
        return copy.deepcopy(context.get("result", {}))
    if kind in ("scope", "plan"):
        brands = list(dict.fromkeys(str(b).strip() for b in context.get("brands", []) if str(b).strip()))
        subject = brands[0] if brands else str(context.get("query", "")).strip()
        if kind == "scope":
            return {"subject": subject, "domain": "", "competitors": brands[1:]}
        return {
            "subject": subject, "category": "", "brands": brands,
            "focus": context.get("focus") or ["Feature comparison", "Pricing strategy", "User sentiment"],
            "search_angles": ["product features", "pricing plans", "user reviews", "latest news",
                              "documentation", "release notes", "customer support", "integrations", "security"]
                             [:context.get("max_angles", 7)],
        }
    if kind == "dispatch":
        scores = context.get("scores", {})
        candidates = sorted(context.get("candidates", []),
                            key=lambda e: (-scores.get(e["id"], 0), e["id"]))
        picked = [e for e in candidates if e["level"] == "L2"][:2]
        picked += [e for e in candidates if e["level"] == "L1"][:4]
        return {"members": [{"id": e["id"], "reason": "[MOCK] Deterministic relevance ranking."}
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
