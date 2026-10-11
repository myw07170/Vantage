"""Mechanical citation checks and one evidence-grounded semantic review chain."""
from __future__ import annotations
import datetime as dt
import math
import re
from collections import Counter, defaultdict
from app.core.models import all_items, now

def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()

def contains_quote(evidence: dict, quote: str) -> bool:
    return len(quote.strip()) >= 8 and normalized(quote) in normalized(evidence.get("context", ""))

def dependent_ids(content: dict, changed: set[str]) -> set[str]:
    affected = set(changed)
    while True:
        added = {i["id"] for i in all_items(content) if set(i.get("depends_on", [])) & affected}
        if added <= affected:
            return affected
        affected |= added

def invalidate(content: dict, changed: set[str]) -> set[str]:
    affected = dependent_ids(content, changed)
    for item in all_items(content):
        if item["id"] in affected:
            item["review"] = {"status": "pending_review", "citation_valid": None, "support_checked": False,
                              "reason": "Content or a dependency was edited. Review again.",
                              "evidence_ids": [], "quotes": [], "checked_at": None}
    content["charts"] = charts(content)
    summarize(content)
    return affected

def citation_problem(item: dict, content: dict, *, structure: bool = True) -> str:
    evidence = {e["evidence_id"]: e for e in content["evidence"]}
    if not item["citations"]:
        return "No supporting evidence was supplied."
    for ref in item["citations"]:
        ev = evidence.get(ref["evidence_id"])
        if not ev:
            return "A citation refers to missing evidence."
        if item["kind"] != "inference" and item["product_id"] and ev["product_id"] != item["product_id"]:
            return "A citation belongs to a different product."
        if not contains_quote(ev, ref["quote"]):
            return "The cited excerpt cannot be located in the stored source context."
    if not structure:
        return ""
    if item["kind"] == "change":
        try:
            date = dt.date.fromisoformat(item["effective_date"] or "")
            if not dt.date.fromisoformat(content["changes_since"][:10]) <= date <= dt.date.fromisoformat(content["checked_at"][:10]):
                return "The release/effective date is outside the confirmed 90-day interval."
        except ValueError:
            return "A verified publication or effective date is required, not a capture date."
    if "value" in item["conditions"]:
        missing = [k for k in ("plan", "currency", "billing_period", "seats", "unit") if not item["conditions"].get(k)]
        if missing:
            return "Numeric pricing is missing comparable billing conditions: " + ", ".join(missing)
    return ""

def apply_reviews(content: dict, items: list[dict], response: dict | None) -> list[dict]:
    evidence = {e["evidence_id"]: e for e in content["evidence"]}
    raw = response.get("reviews", []) if isinstance(response, dict) else []
    raw = raw if isinstance(raw, list) else []
    # Duplicated or missing reviewer outputs cannot silently pass.
    counts = Counter(r.get("item_id") for r in raw if isinstance(r, dict))
    results = {r.get("item_id"): r for r in raw if isinstance(r, dict)}
    for item in items:
        problem = citation_problem(item, content)
        valid = not citation_problem(item, content, structure=False)
        review = {"status": "unknown" if problem else "pending_review", "citation_valid": valid,
                  "support_checked": False, "reason": problem or "Reviewer did not return a usable assessment.",
                  "evidence_ids": [], "quotes": [], "checked_at": now()}
        record = results.get(item["id"])
        if not problem and record and counts[item["id"]] == 1:
            status = record.get("status")
            refs = record.get("evidence_ids", [])
            quotes = record.get("quotes", [])
            quotes = [q for q in quotes if isinstance(q, dict) and isinstance(q.get("quote"), str)] if isinstance(quotes, list) else []
            witnesses = {q.get("evidence_id") for q in quotes if isinstance(q, dict)
                         and q.get("evidence_id") in evidence
                         and contains_quote(evidence[q["evidence_id"]], q.get("quote", ""))
                         and (item["kind"] == "inference" or not item["product_id"] or evidence[q["evidence_id"]]["product_id"] == item["product_id"])}
            own = {r["evidence_id"] for r in item["citations"]}
            grounded = (isinstance(refs, list) and bool(refs) and all(isinstance(r, str) for r in refs) and set(refs) <= witnesses
                        and bool(witnesses & own) and bool(str(record.get("reason", "")).strip()))
            if status == "conflicting" and len(witnesses) < 2:
                grounded = False
            if status in ("supported", "unknown", "conflicting") and grounded:
                review.update(status=status, support_checked=True, reason=record["reason"], evidence_ids=refs,
                              quotes=[q for q in quotes if q.get("evidence_id") in refs])
            else:
                review["reason"] = "Reviewer assessment lacks locatable evidence. Manual or further review is required."
        item["review"] = review
    propagate(content)
    content["charts"] = charts(content)
    summarize(content)
    return [dict(item_id=i["id"], **i["review"]) for i in items if i["review"]["status"] != "supported"]

def propagate(content: dict) -> None:
    items = {i["id"]: i for i in all_items(content)}
    # A conclusion depending on unknown, conflicting or missing facts cannot be supported.
    for _ in range(len(items) + 1):
        changed = False
        for item in items.values():
            if item["review"]["status"] != "supported":
                continue
            bad = [d for d in item["depends_on"] if d not in items or items[d]["review"]["status"] != "supported"]
            if item["kind"] == "inference" and not item["depends_on"]:
                bad = ["missing factual dependencies"]
            if bad:
                item["review"].update(status="unknown", reason="Unresolved dependencies: " + ", ".join(bad))
                changed = True
        if not changed:
            break
    # Cyclic dependencies cannot establish independent support.
    def cyclic(node: str, visiting: set[str], done: set[str]) -> bool:
        if node in visiting:
            return True
        if node in done or node not in items:
            return False
        visiting.add(node)
        result = any(cyclic(d, visiting, done) for d in items[node]["depends_on"])
        visiting.remove(node)
        done.add(node)
        return result
    for item in items.values():
        if cyclic(item["id"], set(), set()):
            item["review"].update(status="pending_review", support_checked=False, reason="Cyclic factual dependencies require review.")
    # Cycle invalidation must also reach conclusions that depend on the cycle.
    for _ in range(len(items)):
        changed = False
        for item in items.values():
            bad = [d for d in item["depends_on"] if d not in items or items[d]["review"]["status"] != "supported"]
            if item["review"]["status"] == "supported" and bad:
                item["review"].update(status="unknown", reason="Unresolved dependencies: " + ", ".join(bad))
                changed = True
        if not changed:
            break

def summarize(content: dict, **extra) -> None:
    counts = Counter(i["review"]["status"] for i in all_items(content))
    content["review_summary"] = {
        **content.get("review_summary", {}), "checked_at": now(), "item_count": len(all_items(content)),
        "counts": {s: counts[s] for s in ("supported", "unknown", "conflicting", "pending_review")},
        "issues": [dict(item_id=i["id"], **i["review"]) for i in all_items(content) if i["review"]["status"] != "supported"],
        "meaning": "Workflow completion does not mean all questions are resolved. Supported means the listed evidence supports this statement under its conditions.",
        **extra,
    }

def charts(content: dict) -> list[dict]:
    groups = defaultdict(list)
    for item in content.get("comparison", []):
        c = item["conditions"]
        value = c.get("value")
        if item["review"]["status"] != "supported" or not isinstance(value, (float, int)) or isinstance(value, bool):
            continue
        if not math.isfinite(value) or value < 0 or citation_problem(item, content):
            continue
        key = tuple((k, str(v)) for k, v in sorted(c.items()) if k != "value")
        groups[key].append(item)
    result = []
    for conditions, items in groups.items():
        if len({i["product_id"] for i in items}) < 2 or len({i["product_id"] for i in items}) != len(items):
            continue
        result.append({"id": "chart-" + items[0]["id"], "conditions": dict(conditions),
                       "points": [{"product_id": i["product_id"], "item_id": i["id"], "value": i["conditions"]["value"],
                                   "citations": i["citations"]} for i in items],
                       "checked_at": content["checked_at"]})
    return result
