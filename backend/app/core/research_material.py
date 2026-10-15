"""Bounded evidence packets and conservative merging for research calls."""
from __future__ import annotations

import json
import re
from collections import defaultdict, deque


def packet_text(e):
    return (f"[{e.evidence_id}|{e.source_type}|{e.brand}|{e.content_kind}] "
            f"{e.source_url}\n{e.title}\n{e.full_text or e.excerpt}")


def evidence_batches(evidences, feedback="", priority_ids=(), budget=18000):
    """Every evidence record is included. Balance brands and prefer repair inputs."""
    priority = set(priority_ids)
    words = set(re.findall(r"[\w-]{3,}", feedback.lower()))
    groups = defaultdict(list)
    for e in evidences:
        groups[e.brand].append(e)
    for brand, rows in groups.items():
        rows.sort(key=lambda e: (e.evidence_id in priority,
                                sum(w in (e.title + " " + (e.full_text or e.excerpt)).lower() for w in words)), reverse=True)
        groups[brand] = deque(rows)
    ordered = []
    while any(groups.values()):
        for rows in groups.values():
            if rows:
                ordered.append(rows.popleft())
    packets, packet, size = [], [], 0
    for e in ordered:
        length = len(packet_text(e))
        if packet and size + length > budget:
            packets.append(packet)
            packet, size = [], 0
        packet.append(e)
        size += length
    if packet:
        packets.append(packet)
    return packets


def unique(rows):
    return list({json.dumps(r, sort_keys=True, ensure_ascii=False): r for r in rows}.values())


def merge_analysis(parts):
    """Never resolve a numeric disagreement by picking an arbitrary batch."""
    result = {"claims": [], "pricing": [], "market_share": [], "comparison": {"dimensions": [], "scores": []},
              "five_forces": {}, "trends": {}, "unknowns": [], "analysis_conflicts": [], "citation_errors": []}
    for part in parts:
        for key in ("claims", "unknowns", "citation_errors"):
            result[key].extend(part.get(key) or [])
        for key in ("pricing", "market_share"):
            for row in part.get(key) or []:
                identity = row.get("brand", row.get("name"))
                old = next((x for x in result[key] if x.get("brand", x.get("name")) == identity), None)
                if old is None:
                    result[key].append(row)
                elif {k: v for k, v in old.items() if k != "evidence_ids"} == {k: v for k, v in row.items() if k != "evidence_ids"}:
                    old["evidence_ids"] = list(dict.fromkeys(old.get("evidence_ids", []) + row.get("evidence_ids", [])))
                else:
                    result["analysis_conflicts"].append(f"Conflicting {key} values for {identity}: {json.dumps([old, row])}")
        comp = part.get("comparison") or {}
        if any(r.get("values") for r in comp.get("scores", [])):
            if not result["comparison"]["dimensions"]:
                result["comparison"] = comp
            elif comp != result["comparison"]:
                if comp.get("dimensions") == result["comparison"]["dimensions"]:
                    existing = result["comparison"]["scores"]
                    for row in comp.get("scores", []):
                        old = next((x for x in existing if x.get("brand") == row.get("brand")), None)
                        if old is None:
                            existing.append(row)
                        elif old.get("values") != row.get("values"):
                            result["analysis_conflicts"].append(f"Conflicting comparison for {row.get('brand')}")
                else:
                    result["analysis_conflicts"].append("Comparison dimensions disagree between evidence packets")
        for key in ("five_forces", "trends"):
            value = part.get(key) or {}
            if value and result[key] and value != result[key]:
                result["analysis_conflicts"].append(f"Conflicting {key} across evidence packets")
            elif value:
                result[key] = value
    for key in ("claims", "unknowns", "analysis_conflicts", "citation_errors"):
        result[key] = unique(result[key])
    return result


def merge_structured(parts):
    out = {"feature_tree": [], "pricing_model": [], "user_persona": []}
    for key, children in (("feature_tree", "modules"), ("pricing_model", "tiers"), ("user_persona", "personas")):
        for part in parts:
            for row in part.get(key, []):
                # Retain competing descriptions for audit instead of overwriting them.
                old = next((x for x in out[key] if x["brand"] == row["brand"] and
                            {k: v for k, v in x.items() if k != children} ==
                            {k: v for k, v in row.items() if k != children}), None)
                if old is None:
                    out[key].append({**row, children: list(row.get(children, []))})
                else:
                    old[children] = unique(old[children] + row.get(children, []))
    return out


def citation_errors(value, valid_ids):
    errors = []
    if isinstance(value, dict):
        ids = value.get("evidence_ids", [])
        if isinstance(ids, list) and any(not isinstance(i, str) or i not in valid_ids for i in ids):
            errors.append({"value": value, "reason": "Citation outside the evidence packet"})
        for child in value.values():
            errors.extend(citation_errors(child, valid_ids))
    elif isinstance(value, list):
        for child in value:
            errors.extend(citation_errors(child, valid_ids))
    return errors
