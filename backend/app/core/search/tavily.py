"""Tavily — second in the chain. Agent-oriented search that returns cleaned
page content alongside results, so hits from here rarely need a fetch.

Free tier at time of writing: 1,000 credits/month (1 credit per basic search).
"""
from __future__ import annotations

from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.search.base import Freshness, SearchUnavailable, now_iso

ENDPOINT = "https://api.tavily.com/search"

name = "tavily"

_TIME_RANGE = {
    Freshness.DAY: "day",
    Freshness.WEEK: "week",
    Freshness.MONTH: "month",
    Freshness.YEAR: "year",
}


def available() -> bool:
    return bool(get_settings().tavily_api_key)


def search(
    query: str,
    *,
    num: int = 10,
    site: Optional[str] = None,
    freshness: str = Freshness.ANY,
) -> list[dict]:
    settings = get_settings()
    if not settings.tavily_api_key:
        raise SearchUnavailable("TAVILY_API_KEY is not set")

    payload: dict = {
        "query": query,
        "max_results": max(1, min(int(num), 20)),
        "search_depth": "basic",  # 1 credit; "advanced" costs 2
        "include_answer": False,
        "include_raw_content": False,
    }
    if site:
        payload["include_domains"] = [d.strip() for d in site.split("|") if d.strip()]
    time_range = _TIME_RANGE.get(freshness)
    if time_range:
        payload["time_range"] = time_range

    timeout = httpx.Timeout(connect=8, read=settings.search_timeout, write=5, pool=5)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.post(
                ENDPOINT,
                headers={
                    "Authorization": f"Bearer {settings.tavily_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError as e:
        raise SearchUnavailable(f"Tavily request failed: {e}") from e

    if r.status_code in (401, 403):
        raise SearchUnavailable("Tavily API key is invalid")
    if r.status_code == 429:
        raise SearchUnavailable("Tavily rate limit or monthly credits exceeded")
    if r.status_code >= 500:
        raise SearchUnavailable(f"Tavily server error (HTTP {r.status_code})")
    if r.status_code != 200:
        raise SearchUnavailable(f"Tavily returned HTTP {r.status_code}: {r.text[:200]}")

    body = r.json() or {}
    out: list[dict] = []
    for item in body.get("results") or []:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or ""
        if not url:
            continue
        content = (item.get("content") or "").strip()
        out.append(
            {
                "title": (item.get("title") or "").strip(),
                "url": url,
                "snippet": content[:500],
                "source": _domain(url),
                "captured_at": item.get("published_date") or now_iso(),
                "content": content or None,
            }
        )
    return out


def _domain(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return (urlparse(url).netloc or "").replace("www.", "")
    except Exception:
        return ""
