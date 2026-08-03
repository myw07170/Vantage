"""Web search with automatic provider failover.

`search()` walks the configured provider chain (SEARCH_PROVIDERS, default
`exa,tavily,ddg`) and returns the first provider's normalized results. A
provider that raises `SearchUnavailable` — bad key, exhausted quota, 5xx — is
skipped and put in a short cooldown so a dead key is not retried on every one
of the ~40 queries a deep run makes.

An empty result set is *not* a failover trigger: the provider worked and found
nothing, and burning a second provider's quota on the same query would not
change that.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Callable, List, Optional

from app.core import trace
from app.core.config import get_settings
from app.core.search import ddg, exa, tavily
from app.core.search.base import Freshness, SearchUnavailable, now_iso

__all__ = ["search", "multi_search", "Freshness", "SearchUnavailable", "provider_status"]

_PROVIDERS = {
    exa.name: exa,
    tavily.name: tavily,
    ddg.name: ddg,
}

# Seconds a provider stays benched after failing.
_COOLDOWN = 300.0
_disabled_until: dict[str, float] = {}
_last_error: dict[str, str] = {}
_lock = threading.Lock()


# Words too common to carry signal when matching a result against a query.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "at", "by",
    "with", "from", "about", "as", "is", "are", "was", "were", "be", "been",
    "vs", "versus", "compare", "comparison", "best", "top", "review", "reviews",
    "how", "what", "why", "which", "who", "when", "where", "does", "do", "did",
    "can", "will", "would", "should", "its", "it", "this", "that", "these",
    "those", "not", "but", "than", "then", "there", "their",
}


def _tokens(text: str) -> list[str]:
    """Content words, lowercased, stopwords removed."""
    raw = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-\.']*", text)
    out = []
    for w in raw:
        lw = w.lower().strip(".-'")
        if len(lw) >= 2 and lw not in _STOPWORDS:
            out.append(lw)
    return out


def _brand_tokens(query: str) -> list[str]:
    """Tokens that look like proper nouns — capitalized mid-sentence, or CamelCase.

    Brand names are the part of a query a result really must match; generic
    terms like "pricing" or "market share" appear on every page.
    """
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-\.']*", query)
    brands = []
    for i, w in enumerate(words):
        lw = w.lower().strip(".-'")
        if len(lw) < 2 or lw in _STOPWORDS:
            continue
        # Skip the first word: sentence-initial capitals prove nothing.
        capitalized = w[0].isupper() and i > 0
        camel = any(c.isupper() for c in w[1:])
        has_digit = any(c.isdigit() for c in w)
        if capitalized or camel or has_digit:
            brands.append(lw)
    return brands


def is_relevant(query: str, title: str, snippet: str) -> bool:
    """Drop results whose title and snippet share nothing with the query.

    Two independent gates:
      * if the query names brands, at least one must appear;
      * at least two content words must appear (one, if that is all there is).
    """
    if not query:
        return True
    text = f"{title} {snippet}".lower()
    if not text.strip():
        return False

    brands = _brand_tokens(query)
    if brands and not any(b in text for b in brands):
        return False

    toks = _tokens(query)
    if not toks:
        return True
    hits = sum(1 for t in toks if t in text)
    return hits >= min(2, len(toks))


def _chain() -> List[str]:
    names = get_settings().search_provider_chain
    return [n for n in names if n in _PROVIDERS]


def _available(name: str) -> bool:
    with _lock:
        until = _disabled_until.get(name, 0.0)
    if until and time.monotonic() < until:
        return False
    provider = _PROVIDERS[name]
    return bool(provider.available())


def _bench(name: str, err: Exception) -> None:
    with _lock:
        _disabled_until[name] = time.monotonic() + _COOLDOWN
        _last_error[name] = str(err)[:200]


def provider_status() -> dict:
    """Which providers are configured and which are currently benched."""
    now = time.monotonic()
    with _lock:
        disabled = dict(_disabled_until)
        errors = dict(_last_error)
    return {
        name: {
            "configured": bool(_PROVIDERS[name].available()),
            "cooling_down": disabled.get(name, 0.0) > now,
            "last_error": errors.get(name, ""),
        }
        for name in _chain()
    }


def search(
    query: str,
    *,
    num: int = 10,
    site: Optional[str] = None,
    freshness: str = Freshness.ANY,
    task_id: str = "",
) -> list[dict]:
    """Search the chain; returns normalized results, relevance-filtered.

    Over-fetches 2x because relevance filtering discards some results.
    """
    count = max(1, min(int(num), 25))
    over = min(count * 2, 25)
    errors: list[str] = []

    for name in _chain():
        if not _available(name):
            continue
        provider = _PROVIDERS[name]
        try:
            raw = provider.search(query, num=over, site=site, freshness=freshness)
        except SearchUnavailable as e:
            _bench(name, e)
            errors.append(f"{name}: {e}")
            continue
        except Exception as e:  # noqa: BLE001 — never let one provider kill a run
            _bench(name, e)
            errors.append(f"{name}: {e}")
            continue

        results = [
            r for r in raw if is_relevant(query, r.get("title", ""), r.get("snippet", ""))
        ][:count]
        if task_id:
            try:
                trace.record_manual_span(
                    task_id=task_id,
                    agent_id="",
                    stage="collect",
                    purpose=f"Web search via {name}",
                    detail=f"query: {query}\nsite: {site or '-'}\nfreshness: {freshness}",
                    decision=f"{len(results)} results kept of {len(raw)} returned",
                    model=f"— (search: {name})",
                )
            except Exception:
                pass
        return results

    raise SearchUnavailable(
        "No search provider is available. " + ("; ".join(errors) if errors else
        "Set EXA_API_KEY or TAVILY_API_KEY in backend/.env, or keep 'ddg' in "
        "SEARCH_PROVIDERS for keyless local development.")
    )


def multi_search(
    queries: List[str],
    *,
    num: int = 10,
    site: Optional[str] = None,
    freshness: str = Freshness.ANY,
    task_id: str = "",
) -> list[dict]:
    """Run several queries and merge, de-duplicating by URL.

    Best-effort: one failing query does not abort the rest, so a partial
    evidence set still reaches the analysis stage.
    """
    seen: set[str] = set()
    out: list[dict] = []
    for q in queries:
        try:
            for r in search(
                q, num=num, site=site, freshness=freshness, task_id=task_id
            ):
                url = r.get("url", "")
                key = url or r.get("title", "")
                if not key or key in seen:
                    continue
                seen.add(key)
                r["query"] = q
                out.append(r)
        except Exception:
            continue
    return out
