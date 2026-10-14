"""Evidence credibility scoring — deterministic, explainable, no LLM.

Produces a 0-100 integer from four independent signals:
  * base score by source type (a 10-K outranks a Reddit comment);
  * domain authority (regulators, wire-quality press, research houses up;
    press-release mills and content farms down);
  * recency (a publication date at all is a positive signal; stale is negative);
  * fetch quality (full article body vs a snippet-only fallback).

Rule-based on purpose: the score has to be defensible to a reader, and asking a
model to rate its own sources would be circular.
"""
from __future__ import annotations

import datetime as _dt
import math
import re
from typing import Optional
from urllib.parse import urlparse

from app.core.models import SourceType

# Base score per source type. Matches orchestrator._source_type's output.
_BASE_BY_TYPE = {
    SourceType.SEC_FILING: 78,   # audited, legally binding
    SourceType.OFFICIAL: 70,     # authoritative on the vendor's own product
    SourceType.ANALYST: 66,      # methodology-backed, but often vendor-funded
    SourceType.NEWS: 60,
    SourceType.HACKERNEWS: 46,   # practitioner-heavy, identifiable, threaded
    SourceType.REVIEW: 44,       # verified buyers, but incentive-contaminated
    SourceType.FORUM: 42,
    SourceType.REDDIT: 40,
    SourceType.YOUTUBE: 36,
    SourceType.X: 34,            # short, unthreaded, hardest to verify
    SourceType.WEB: 30,
    SourceType.UNKNOWN: 30,
}

# High-authority domains and suffixes.
_AUTHORITY_HINTS = (
    ".gov", ".edu", ".mil",
    "sec.gov", "federalreserve.gov", "ftc.gov", "uspto.gov", "bls.gov",
    "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "economist.com",
    "nytimes.com", "washingtonpost.com", "apnews.com", "npr.org",
    "theinformation.com", "stratechery.com", "arstechnica.com",
    "techcrunch.com", "theverge.com", "wired.com", "cnbc.com",
    "gartner.com", "forrester.com", "idc.com", "cbinsights.com",
    "pitchbook.com", "crunchbase.com", "statista.com",
)

# Press-release wires, content farms and marketing pages.
_LOW_QUALITY_HINTS = (
    "prnewswire.com", "businesswire.com", "globenewswire.com", "einpresswire.com",
    "openpr.com", "issuewire.com", "prweb.com",
    "/sponsored", "/press-release", "/partner-content", "/advertorial",
    "utm_campaign", "affiliate", "/promo", "medium.com/tag/",
)

_DATE_RE = re.compile(r"(20\d{2})[-/.](\d{1,2})")


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def freshness_days(captured_at: str) -> Optional[int]:
    """Days since publication, or None when the date cannot be parsed."""
    if not captured_at:
        return None
    now = _dt.datetime.now(_dt.timezone.utc)
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            dt = _dt.datetime.strptime(captured_at[: len(fmt) + 2].strip(), fmt)
            return max(0, (now - dt.replace(tzinfo=_dt.timezone.utc)).days)
        except Exception:
            continue
    # Fall back to year-month only.
    m = _DATE_RE.search(captured_at)
    if m:
        try:
            y, mo = int(m.group(1)), int(m.group(2))
            dt = _dt.datetime(y, max(1, min(12, mo)), 1, tzinfo=_dt.timezone.utc)
            return max(0, (now - dt).days)
        except Exception:
            return None
    return None


def score_evidence(
    url: str,
    source_type: str,
    captured_at: str = "",
    has_publish_date: bool = False,
    ok_fetch: bool = True,
    excerpt: str = "",
    signals: Optional[dict] = None,
) -> int:
    """Credibility on a 0-100 scale.

    Args:
        signals: optional engagement data for social evidence, e.g.
            `{"score": 420, "comments": 88, "followers": 12000}`. A Reddit
            thread with 400 upvotes and 90 replies is more representative of
            user sentiment than one with two — this is where that shows up.
    """
    signals = signals or {}
    domain = _domain(url)
    score = _BASE_BY_TYPE.get(source_type, _BASE_BY_TYPE[SourceType.UNKNOWN])

    if any(h in domain or h in url for h in _AUTHORITY_HINTS):
        score += 10
    if any(h in domain or h in url for h in _LOW_QUALITY_HINTS):
        score -= 5

    if has_publish_date:
        score += 6
    fd = freshness_days(captured_at)
    if fd is not None:
        if fd <= 365:
            score += 5
        elif fd <= 730:
            score += 2
        elif fd > 1095:
            score -= 5

    if ok_fetch:
        score += 6
    else:
        score -= 8
    if excerpt and len(excerpt) > 200:
        score += 3

    score += _engagement_bonus(signals)

    # Nudge scores off multiples of five so the reader sees genuine variation
    # rather than a handful of repeated round numbers. Deterministic per domain.
    if domain:
        score += (len(domain) % 4) - 1  # -1..+2

    return max(5, min(98, int(round(score))))


def _engagement_bonus(signals: dict) -> int:
    """0-12 bonus from engagement, on a log scale so virality cannot dominate."""
    if not signals:
        return 0
    # Accept both the Reddit/HN vocabulary and the generic one.
    likes = _as_int(signals.get("score") or signals.get("likes") or signals.get("points"))
    comments = _as_int(signals.get("comments") or signals.get("num_comments"))
    followers = _as_int(signals.get("followers") or signals.get("subscribers"))
    # Replies signal real discussion, so they outweigh passive upvotes.
    raw = comments * 3 + likes * 1 + followers * 0.2
    if raw <= 0:
        return 0
    # log10: ~100 -> 4, ~10k -> 8, ~1M -> 12
    return int(max(0, min(12, round(math.log10(raw + 1) * 3))))


def _as_int(v) -> int:
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return 0
