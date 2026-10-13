"""Exa — primary provider. Neural search, ranks by meaning rather than keywords.

Free tier at time of writing: $20 signup credit plus $10/month recurring,
roughly 1,400 searches per month at $7/1k.
"""
from __future__ import annotations

from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.search.base import Freshness, SearchUnavailable, now_iso

ENDPOINT = "https://api.exa.ai/search"

name = "exa"


def available() -> bool:
    return bool(get_settings().exa_api_key)


def search(
    query: str,
    *,
    num: int = 10,
    site: Optional[str] = None,
    freshness: str = Freshness.ANY,
) -> list[dict]:
    settings = get_settings()
    if not settings.exa_api_key:
        raise SearchUnavailable("EXA_API_KEY is not set")

    payload: dict = {
        "query": query,
        "numResults": max(1, min(int(num), 25)),
        "type": "auto",
        # Ask for page text up front so the collector can often skip fetching.
        "contents": {"text": {"maxCharacters": 4000}},
    }
    if site:
        payload["includeDomains"] = [d.strip() for d in site.split("|") if d.strip()]
    start = Freshness.to_start_date(freshness)
    if start:
        payload["startPublishedDate"] = start

    timeout = httpx.Timeout(connect=8, read=settings.search_timeout, write=5, pool=5)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.post(
                ENDPOINT,
                headers={
                    "x-api-key": settings.exa_api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError as e:
        raise SearchUnavailable(f"Exa request failed: {e}") from e

    if r.status_code in (401, 403):
        raise SearchUnavailable("Exa API key is invalid or out of credit")
    if r.status_code == 429:
        raise SearchUnavailable("Exa rate limit exceeded")
    if r.status_code >= 500:
        raise SearchUnavailable(f"Exa server error (HTTP {r.status_code})")
    if r.status_code != 200:
        raise SearchUnavailable(f"Exa returned HTTP {r.status_code}: {r.text[:200]}")

    body = r.json() or {}
    out: list[dict] = []
    for item in body.get("results") or []:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or ""
        if not url:
            continue
        text = (item.get("text") or "").strip()
        out.append(
            {
                "title": (item.get("title") or "").strip(),
                "url": url,
                # Exa returns full text, not a snippet; keep a short lead for
                # prompts and hand the full body to the collector separately.
                "snippet": text[:500],
                "source": item.get("author") or _domain(url),
                "captured_at": item.get("publishedDate") or now_iso(),
                "content": text or None,
            }
        )
    return out


def _domain(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return (urlparse(url).netloc or "").replace("www.", "")
    except Exception:
        return ""
