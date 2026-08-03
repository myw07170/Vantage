"""DuckDuckGo — keyless last resort.

No signup and no quota, which makes it the right default for local development
and a safety net when the metered providers are exhausted. It is scraped rather
than an official API, so it rate-limits aggressively and returns snippets only
(no page content). Do not rely on it for a demo.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from app.core.search.base import Freshness, SearchUnavailable, now_iso

name = "ddg"

_TIMELIMIT = {
    Freshness.DAY: "d",
    Freshness.WEEK: "w",
    Freshness.MONTH: "m",
    Freshness.YEAR: "y",
}

# DuckDuckGo blocks bursts, so serialize and space out queries.
_lock = threading.Lock()
_last_call = 0.0
_MIN_INTERVAL = 2.0


def available() -> bool:
    return True  # no key required


def search(
    query: str,
    *,
    num: int = 10,
    site: Optional[str] = None,
    freshness: str = Freshness.ANY,
) -> list[dict]:
    global _last_call
    try:
        from ddgs import DDGS
    except ImportError as e:  # pragma: no cover
        raise SearchUnavailable("ddgs is not installed") from e

    q = query
    if site:
        # DuckDuckGo has no domain-filter parameter; express it in the query.
        domains = [d.strip() for d in site.split("|") if d.strip()]
        if domains:
            q = f"{query} ({' OR '.join('site:' + d for d in domains)})"

    kwargs: dict = {"max_results": max(1, min(int(num), 25)), "region": "us-en"}
    timelimit = _TIMELIMIT.get(freshness)
    if timelimit:
        kwargs["timelimit"] = timelimit

    with _lock:
        gap = time.monotonic() - _last_call
        if gap < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - gap)
        try:
            rows = DDGS().text(q, **kwargs) or []
        except Exception as e:  # noqa: BLE001
            raise SearchUnavailable(f"DuckDuckGo request failed: {e}") from e
        finally:
            _last_call = time.monotonic()

    out: list[dict] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        url = item.get("href") or item.get("url") or ""
        if not url:
            continue
        body = (item.get("body") or "").strip()
        out.append(
            {
                "title": (item.get("title") or "").strip(),
                "url": url,
                "snippet": body[:500],
                "source": _domain(url),
                "captured_at": now_iso(),
                "content": None,  # snippets only — the fetcher must do the work
            }
        )
    return out


def _domain(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return (urlparse(url).netloc or "").replace("www.", "")
    except Exception:
        return ""
