"""Sentiment analysis over collected user voice.

Every comment analyzed here is a real one, retrieved with a working source URL.
When nothing is found the result is an honest empty structure — no synthesized
sample, no placeholder percentages.

Classification prefers the LLM and falls back to keyword rules. Camp shares are
normalized so the three groups sum to exactly 100.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.core.llm import chat_json
from app.core.platforms import PLATFORM_LABEL, PLATFORM_ORDER

# Keyword fallback for when the LLM is unavailable. Deliberately short and
# high-precision — this is a safety net, not the primary classifier.
_POS = [
    "love", "great", "excellent", "recommend", "worth it", "solid", "best",
    "fantastic", "reliable", "intuitive", "smooth", "impressed", "game changer",
]
_NEG = [
    "terrible", "awful", "expensive", "overpriced", "buggy", "broken", "slow",
    "disappointed", "clunky", "frustrating", "cancelled", "avoid", "regret",
    "unusable", "waste of money",
]


def _empty_result() -> Dict[str, Any]:
    """Honest empty structure when no real comments were found."""
    return {
        "overall": {"pos": 0, "neu": 0, "neg": 0},
        "overall_count": {"pos": 0, "neu": 0, "neg": 0},
        "by_platform": {},
        "by_brand": [],
        "timeline": [],
        "camps": [],
        "voices": [],
        "highlights": [],
        "sample_size": 0,
    }


def _rule_sentiment(text: str) -> str:
    low = (text or "").lower()
    p = sum(w in low for w in _POS)
    n = sum(w in low for w in _NEG)
    if p > n:
        return "pos"
    if n > p:
        return "neg"
    return "neu"


def _llm_classify(brand: str, comments: List[Dict[str, Any]], model: str = None) -> bool:
    """Label each comment pos/neu/neg, writing back to `comment["sentiment"]`.

    Returns False if the call fails, so the caller can fall back to rules.
    """
    if not comments:
        return False
    items = [
        {"i": i, "text": (c.get("text") or "")[:300]} for i, c in enumerate(comments)
    ]
    try:
        data = chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a social-listening analyst. For each user comment, "
                        "judge its sentiment toward the target brand specifically — "
                        "not the general tone of the post. A comment praising a "
                        "competitor while criticizing the target is negative."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Target brand: {brand}\n\n"
                        "Classify each comment as exactly one of: pos (positive / "
                        "favorable), neu (neutral / comparing, undecided), neg "
                        "(negative / critical).\n"
                        'Return a JSON array of {"i": <index>, "s": "pos|neu|neg"} '
                        "where i matches the input index.\n\n"
                        f"Comments:\n{items}"
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=1500,
            model=model,
            purpose="Classify sentiment of collected user comments",
        )
    except Exception:
        # Any model failure — bad key, quota, timeout — falls back to the
        # keyword rules rather than aborting a run that already has real
        # evidence in hand.
        return False
    # The model may return a bare array or wrap it in an object.
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                data = v
                break
    if not isinstance(data, list):
        return False
    mapping = {}
    for it in data:
        if isinstance(it, dict) and "i" in it and it.get("s") in ("pos", "neu", "neg"):
            try:
                mapping[int(it["i"])] = it["s"]
            except (TypeError, ValueError):
                continue
    if not mapping:
        return False
    for i, c in enumerate(comments):
        c["sentiment"] = mapping.get(i) or _rule_sentiment(c.get("text", ""))
    return True


def analyze_sentiment(
    brand: str, comments: List[Dict[str, Any]], model: str = None
) -> Dict[str, Any]:
    """comments: `[{text, platform, url, title, brand, signals?}]`, all real."""
    if not comments:
        return _empty_result()

    if not _llm_classify(brand, comments, model=model):
        for c in comments:
            c["sentiment"] = _rule_sentiment(c.get("text", ""))

    overall = {"pos": 0, "neu": 0, "neg": 0}
    by_platform: Dict[str, Dict[str, int]] = {}
    for c in comments:
        s = c.get("sentiment", "neu")
        overall[s] = overall.get(s, 0) + 1
        plat = c.get("platform") or "web"
        by_platform.setdefault(plat, {"pos": 0, "neu": 0, "neg": 0})
        by_platform[plat][s] += 1

    total = max(sum(overall.values()), 1)
    overall_pct = _normalize_pct(overall, total)
    camps = _build_camps(brand, comments, total)
    voices = _build_voices(comments)
    highlights = _extract_highlights(brand, comments, model=model)

    # Present platforms in registry priority order.
    ordered_platform = {p: by_platform[p] for p in PLATFORM_ORDER if p in by_platform}
    for p in by_platform:
        if p not in ordered_platform:
            ordered_platform[p] = by_platform[p]

    return {
        "overall": overall_pct,
        "overall_count": overall,
        "by_platform": ordered_platform,
        "by_brand": _build_by_brand(comments),
        # Comments carry no dependable publication dates, so a timeline would be
        # fabricated. Left empty on purpose.
        "timeline": [],
        "camps": camps,
        "voices": voices,
        "highlights": highlights,
        "sample_size": len(comments),
    }


def _build_by_brand(comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sentiment split per brand, for side-by-side comparison."""
    agg: Dict[str, Dict[str, int]] = {}
    for c in comments:
        b = (c.get("brand") or "").strip()
        if not b:
            continue
        s = c.get("sentiment", "neu")
        agg.setdefault(b, {"pos": 0, "neu": 0, "neg": 0})
        agg[b][s] += 1
    out: List[Dict[str, Any]] = []
    for b, counts in agg.items():
        n = counts["pos"] + counts["neu"] + counts["neg"]
        if not n:
            continue
        pct = _normalize_pct(counts, n)
        out.append(
            {
                "brand": b,
                "sample": n,
                "pos": pct["pos"],
                "neu": pct["neu"],
                "neg": pct["neg"],
            }
        )
    out.sort(key=lambda x: x["sample"], reverse=True)
    return out


def _build_voices(comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Representative verbatims per platform, each with a working source link."""
    by_plat: Dict[str, List[Dict[str, Any]]] = {}
    for c in comments:
        by_plat.setdefault(c.get("platform") or "web", []).append(c)
    voices: List[Dict[str, Any]] = []
    plats = [p for p in PLATFORM_ORDER if p in by_plat] + [
        p for p in by_plat if p not in PLATFORM_ORDER
    ]
    for plat in plats:
        items = [
            c for c in by_plat[plat] if c.get("url") and (c.get("text") or "").strip()
        ]
        # Opinionated comments carry more information than neutral ones; within
        # that, prefer the most-engaged.
        items.sort(
            key=lambda c: (
                0 if c.get("sentiment") in ("pos", "neg") else 1,
                -int((c.get("signals") or {}).get("score", 0) or 0),
            )
        )
        for c in items[:3]:
            voices.append(
                {
                    "platform": plat,
                    "platform_label": PLATFORM_LABEL.get(plat, plat),
                    "text": (c.get("text") or "").strip()[:220],
                    "sentiment": c.get("sentiment", "neu"),
                    "url": c.get("url", ""),
                    "title": c.get("title", ""),
                }
            )
    return voices


def _extract_highlights(
    brand: str, comments: List[Dict[str, Any]], model: str = None
) -> List[Dict[str, Any]]:
    """Pull the most telling phrases, each still linked to its source comment."""
    pool = [c for c in comments if c.get("url") and (c.get("text") or "").strip()]
    if not pool:
        return []
    items = [
        {
            "i": i,
            "text": (c.get("text") or "")[:250],
            "platform": PLATFORM_LABEL.get(c.get("platform", ""), ""),
        }
        for i, c in enumerate(pool)
    ]
    try:
        data = chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a social-listening analyst. From these real user "
                        "comments, pull the 4-6 most revealing short phrases — the "
                        "lines that best capture what people actually think. Cover "
                        "both positive and negative voices.\n\n"
                        "Quote or tightly condense the user's own words. Never "
                        "invent a phrase that is not supported by the comment.\n"
                        'Return a JSON array of {"i": <original index>, '
                        '"phrase": "<under 90 characters>"}.'
                    ),
                },
                {
                    "role": "user",
                    "content": f"Target brand: {brand}\nComments:\n{items}",
                },
            ],
            temperature=0.3,
            max_tokens=800,
            model=model,
            purpose="Extract representative quotes from user comments",
        )
    except Exception:
        return []
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                data = v
                break
    if not isinstance(data, list):
        return []
    out: List[Dict[str, Any]] = []
    for it in data:
        if not isinstance(it, dict) or "i" not in it or not it.get("phrase"):
            continue
        try:
            src = pool[int(it["i"])]
        except (ValueError, IndexError, TypeError):
            continue
        out.append(
            {
                "phrase": str(it["phrase"])[:120],
                "platform": src.get("platform", ""),
                "platform_label": PLATFORM_LABEL.get(src.get("platform", ""), ""),
                "sentiment": src.get("sentiment", "neu"),
                "url": src.get("url", ""),
            }
        )
    return out[:6]


def _normalize_pct(counts: Dict[str, int], total: int) -> Dict[str, int]:
    """Counts to percentages summing to exactly 100 (largest remainder)."""
    keys = list(counts.keys())
    raw = {k: counts[k] / total * 100 for k in keys}
    floored = {k: int(raw[k]) for k in keys}
    remainder = 100 - sum(floored.values())
    order = sorted(keys, key=lambda k: raw[k] - floored[k], reverse=True)
    for k in order[: max(remainder, 0)]:
        floored[k] += 1
    return floored


def _build_camps(
    brand: str, comments: List[Dict[str, Any]], total: int
) -> List[Dict[str, Any]]:
    """Group opinion into three camps with normalized shares and real quotes."""
    pos = [c for c in comments if c.get("sentiment") == "pos"]
    neg = [c for c in comments if c.get("sentiment") == "neg"]
    neu = [c for c in comments if c.get("sentiment") == "neu"]

    groups = [
        (
            pos,
            "pos",
            f"Advocates — sold on {brand}",
            f"These users credit {brand} with delivering on experience, value or reliability.",
        ),
        (
            neg,
            "neg",
            f"Skeptics — wary of {brand}",
            f"These users raise concrete concerns about {brand}'s price, stability or support.",
        ),
        (
            neu,
            "neu",
            "Undecided — still comparing",
            "These users are weighing options and have not committed either way.",
        ),
    ]
    counts = {"pos": len(pos), "neg": len(neg), "neu": len(neu)}
    pct = _normalize_pct(counts, max(total, 1))

    camps: List[Dict[str, Any]] = []
    for group, key, title, summary in groups:
        if not group:
            continue
        quotes = [
            {
                "text": c.get("text", "")[:220],
                "url": c.get("url", ""),
                "platform": PLATFORM_LABEL.get(c.get("platform", ""), ""),
            }
            for c in group[:4]
            if c.get("url")
        ]
        camps.append(
            {
                "title": title,
                "ratio": pct[key],
                "summary": summary,
                "quotes": quotes,
            }
        )
    return camps
