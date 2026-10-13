"""Bounded, product-balanced source context shared by analysis and review.

Ranking is a retrieval heuristic, not an assessment of factual support.
"""
from __future__ import annotations

import re
from collections import deque
from typing import Any, Iterable


def value(source: Any, key: str, default: Any = "") -> Any:
    return source.get(key, default) if isinstance(source, dict) else getattr(source, key, default)


def source_text(source: Any) -> str:
    return str(value(source, "full_text") or value(source, "excerpt") or "")


def terms(dimensions: Iterable[str]) -> set[str]:
    text = " ".join(dimensions).lower().replace("_", " ")
    found = set(re.findall(r"[a-z0-9]{3,}|[\u4e00-\u9fff]+", text))
    for markers, related in [
        (("pricing", "price", "定价", "价格"), "pricing price cost billing subscription plan seat free monthly annual usd"),
        (("feature", "功能", "technical"), "feature capability integration support api architecture security"),
        (("sentiment", "用户", "persona"), "user review customer developer workflow feedback"),
        (("trend", "变化"), "release changelog update announcement launch"),
    ]:
        if any(m in text for m in markers):
            found.update(related.split())
    return found - {"comparison", "strategy", "model", "tree", "overview", "summary"}


def select_evidence(sources: list, *, brands: list[str], dimensions: list[str],
                    limit: int, priority_ids: Iterable[str] = ()) -> list:
    """Round-robin across products, ranked within each product; deterministic.

Claim citations rank first within their product. No product can consume all
slots simply because its sources were collected first.
"""
    keywords = terms(dimensions)
    priority = set(priority_ids)
    groups: dict[str, list] = {b: [] for b in brands}
    seen: set[str] = set()
    for source in sources:
        eid = value(source, "evidence_id")
        if not eid or eid in seen:
            continue
        seen.add(eid)
        groups.setdefault(value(source, "brand"), []).append(source)

    def rank(source):
        text = (str(value(source, "title")) + " " + source_text(source)).lower()
        return (-int(value(source, "evidence_id") in priority),
                -sum(t in text for t in keywords),
                -int(value(source, "source_type") == "official"),
                -float(value(source, "credibility", 0) or 0),
                str(value(source, "source_url")), str(value(source, "evidence_id")))

    queues = [deque(sorted(rows, key=rank)) for rows in groups.values() if rows]
    selected = []
    while queues and len(selected) < limit:
        remaining = []
        for queue in queues:
            if len(selected) == limit:
                break
            selected.append(queue.popleft())
            if queue:
                remaining.append(queue)
        queues = remaining
    return selected


def evidence_digest(selected: list, *, brands: list[str] = (),
                    dimensions: list[str] = (), max_chars: int = 1500) -> str:
    lines = []
    for source in selected:
        lines.append(
            f"[{value(source, 'evidence_id')}|{value(source, 'brand')}|"
            f"{value(source, 'source_type')}|{value(source, 'domain')}] "
            f"{value(source, 'title')} (published: {value(source, 'published_at') or 'unknown'}):\n"
            + source_text(source)[:max_chars]
        )
    keywords = terms(dimensions)
    for brand in brands:
        rows = [s for s in selected if value(s, "brand") == brand]
        if not rows:
            lines.append(f"COLLECTION GAP: no source context supplied for {brand}.")
        elif keywords and not any(any(t in (str(value(s, 'title')) + ' ' + source_text(s)).lower()
                                      for t in keywords) for s in rows):
            lines.append(f"RETRIEVAL GAP: no matching context for {brand} on {', '.join(dimensions)}; do not infer missing facts.")
    return "\n\n".join(lines) or "(no source context supplied)"
