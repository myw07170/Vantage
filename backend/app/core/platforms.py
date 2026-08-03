"""Social-listening platform registry.

Each platform declares how to reach it. Two collection strategies:

* **API** — Reddit and Hacker News expose real endpoints, so we read actual
  comment bodies with their scores and reply counts. That is a materially
  better sample than a search snippet, and the engagement numbers feed
  `credibility._engagement_bonus`.
* **Search** — everything else is reached through site-restricted web search.
  Snippets only, but it needs no credentials and covers review sites that have
  no public API.

Adding a platform means adding one `Platform` entry; nothing downstream of the
registry knows the difference.
"""
from __future__ import annotations

import datetime as _dt
import html
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import httpx

from app.core.config import get_settings
from app.core.models import SourceType


@dataclass
class Platform:
    key: str
    label: str
    domain: str
    source_type: str
    #: Lower sorts first in the report's platform breakdown.
    priority: int = 50
    #: Query templates; `{brand}` and `{category}` are substituted.
    query_templates: List[str] = field(
        default_factory=lambda: [
            "{brand} {category} review",
            "{brand} {category} pros and cons",
            "{brand} vs alternatives {category}",
        ]
    )
    #: None means "collect via site-restricted web search".
    collector: Optional[Callable[..., List[Dict[str, Any]]]] = None

    def queries(self, brand: str, category: str = "") -> List[str]:
        # Templates embed `{category}` directly against `{brand}`, so the
        # separating space has to come from the substituted value.
        cat = f" {category.strip()}" if category and category.strip() else ""
        return [
            re.sub(r"\s+", " ", t.format(brand=brand, category=cat)).strip()
            for t in self.query_templates
        ]


# ── Hacker News (Algolia — public, no credentials) ────────────────────────────

_HN_ENDPOINT = "https://hn.algolia.com/api/v1/search"


def collect_hackernews(
    brand: str, category: str = "", *, limit: int = 12
) -> List[Dict[str, Any]]:
    """Real HN comments and stories mentioning the brand.

    Algolia's HN index is public and unauthenticated. Comments carry author,
    points and reply counts, and every item maps back to a permalink.
    """
    out: List[Dict[str, Any]] = []
    query = f"{brand} {category}".strip()
    try:
        with httpx.Client(timeout=httpx.Timeout(connect=8, read=20, write=5, pool=5)) as c:
            r = c.get(
                _HN_ENDPOINT,
                params={
                    "query": query,
                    "tags": "(story,comment)",
                    "hitsPerPage": min(limit * 2, 50),
                },
            )
            if r.status_code != 200:
                return []
            hits = (r.json() or {}).get("hits") or []
    except Exception:
        return []

    for h in hits:
        if not isinstance(h, dict):
            continue
        text = _strip_html(h.get("comment_text") or h.get("story_text") or "")
        title = (h.get("title") or h.get("story_title") or "").strip()
        if not text and not title:
            continue
        body = text or title
        # Require the brand to actually appear — Algolia matches loosely.
        if brand.lower() not in body.lower() and brand.lower() not in title.lower():
            continue
        object_id = h.get("objectID")
        if not object_id:
            continue
        out.append(
            {
                "text": body[:600],
                "platform": "hackernews",
                "url": f"https://news.ycombinator.com/item?id={object_id}",
                "title": title or f"Hacker News discussion: {brand}",
                "brand": brand,
                "author": h.get("author") or "",
                "created_at": h.get("created_at") or "",
                "signals": {
                    "score": _int(h.get("points")),
                    "comments": _int(h.get("num_comments")),
                },
            }
        )
        if len(out) >= limit:
            break
    return out


# ── Reddit (OAuth client-credentials) ─────────────────────────────────────────

_REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_REDDIT_SEARCH_URL = "https://oauth.reddit.com/search"
_token_lock = threading.Lock()
_token_cache: Dict[str, Any] = {"value": "", "expires": 0.0}


def _reddit_token() -> str:
    """Application-only OAuth token, cached until shortly before expiry."""
    s = get_settings()
    if not s.reddit_client_id or not s.reddit_client_secret:
        return ""
    with _token_lock:
        if _token_cache["value"] and time.time() < _token_cache["expires"]:
            return str(_token_cache["value"])
        try:
            with httpx.Client(timeout=20) as c:
                r = c.post(
                    _REDDIT_TOKEN_URL,
                    auth=(s.reddit_client_id, s.reddit_client_secret),
                    data={"grant_type": "client_credentials"},
                    headers={"User-Agent": s.reddit_user_agent},
                )
            if r.status_code != 200:
                return ""
            body = r.json() or {}
            token = body.get("access_token") or ""
            if token:
                _token_cache["value"] = token
                _token_cache["expires"] = time.time() + int(body.get("expires_in", 3600)) - 120
            return str(token)
        except Exception:
            return ""


def collect_reddit(
    brand: str, category: str = "", *, limit: int = 12
) -> List[Dict[str, Any]]:
    """Real Reddit posts mentioning the brand, with score and comment counts.

    Returns an empty list when credentials are absent, which makes the caller
    fall back to site-restricted web search.
    """
    token = _reddit_token()
    if not token:
        return []
    s = get_settings()
    query = f"{brand} {category}".strip()
    try:
        with httpx.Client(timeout=httpx.Timeout(connect=8, read=20, write=5, pool=5)) as c:
            r = c.get(
                _REDDIT_SEARCH_URL,
                params={
                    "q": query,
                    "limit": min(limit * 2, 50),
                    "sort": "relevance",
                    "t": "year",
                    "type": "link",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": s.reddit_user_agent,
                },
            )
        if r.status_code != 200:
            return []
        children = ((r.json() or {}).get("data") or {}).get("children") or []
    except Exception:
        return []

    out: List[Dict[str, Any]] = []
    for ch in children:
        d = (ch or {}).get("data") or {}
        title = (d.get("title") or "").strip()
        body = (d.get("selftext") or "").strip()
        text = f"{title}. {body}".strip(". ").strip()
        if not text:
            continue
        if brand.lower() not in text.lower():
            continue
        permalink = d.get("permalink") or ""
        if not permalink:
            continue
        out.append(
            {
                "text": text[:600],
                "platform": "reddit",
                "url": f"https://www.reddit.com{permalink}",
                "title": title,
                "brand": brand,
                "author": d.get("author") or "",
                "subreddit": d.get("subreddit") or "",
                "created_at": _epoch_iso(d.get("created_utc")),
                "signals": {
                    "score": _int(d.get("score")),
                    "comments": _int(d.get("num_comments")),
                    "followers": _int(d.get("subreddit_subscribers")),
                },
            }
        )
        if len(out) >= limit:
            break
    return out


# ── Registry ──────────────────────────────────────────────────────────────────

PLATFORMS: Dict[str, Platform] = {
    "reddit": Platform(
        key="reddit",
        label="Reddit",
        domain="reddit.com",
        source_type=SourceType.REDDIT,
        priority=10,
        collector=collect_reddit,
        query_templates=[
            "{brand}{category} review",
            "{brand}{category} worth it",
            "switching from {brand}{category}",
        ],
    ),
    "hackernews": Platform(
        key="hackernews",
        label="Hacker News",
        domain="news.ycombinator.com",
        source_type=SourceType.HACKERNEWS,
        priority=20,
        collector=collect_hackernews,
        query_templates=["{brand}{category}"],
    ),
    "g2": Platform(
        key="g2",
        label="G2",
        domain="g2.com",
        source_type=SourceType.REVIEW,
        priority=30,
        query_templates=[
            "{brand}{category} reviews",
            "{brand}{category} pros and cons",
        ],
    ),
    "trustpilot": Platform(
        key="trustpilot",
        label="Trustpilot",
        domain="trustpilot.com",
        source_type=SourceType.REVIEW,
        priority=40,
        query_templates=["{brand}{category} reviews", "{brand}{category} complaints"],
    ),
    "capterra": Platform(
        key="capterra",
        label="Capterra",
        domain="capterra.com",
        source_type=SourceType.REVIEW,
        priority=50,
        query_templates=["{brand}{category} reviews"],
    ),
    "youtube": Platform(
        key="youtube",
        label="YouTube",
        domain="youtube.com",
        source_type=SourceType.YOUTUBE,
        priority=60,
        query_templates=["{brand}{category} review", "{brand}{category} honest opinion"],
    ),
    "x": Platform(
        key="x",
        label="X",
        domain="x.com|twitter.com",
        source_type=SourceType.X,
        priority=70,
        query_templates=["{brand}{category} opinion"],
    ),
}

PLATFORM_ORDER: List[str] = sorted(PLATFORMS, key=lambda k: PLATFORMS[k].priority)
PLATFORM_LABEL: Dict[str, str] = {k: p.label for k, p in PLATFORMS.items()}
PLATFORM_SITES: Dict[str, str] = {k: p.domain for k, p in PLATFORMS.items()}
PLATFORM_SOURCE_TYPE: Dict[str, str] = {k: p.source_type for k, p in PLATFORMS.items()}


def get_platform(key: str) -> Optional[Platform]:
    return PLATFORMS.get(key)


def api_platforms() -> List[Platform]:
    """Platforms with a real API collector, in priority order."""
    return [PLATFORMS[k] for k in PLATFORM_ORDER if PLATFORMS[k].collector]


def search_platforms() -> List[Platform]:
    """Platforms collected through site-restricted web search."""
    return [PLATFORMS[k] for k in PLATFORM_ORDER if not PLATFORMS[k].collector]


# ── helpers ───────────────────────────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return html.unescape(_TAG_RE.sub(" ", text)).replace("\xa0", " ").strip()


def _int(v) -> int:
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return 0


def _epoch_iso(v) -> str:
    try:
        return _dt.datetime.fromtimestamp(float(v), _dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except (TypeError, ValueError, OSError):
        return ""
