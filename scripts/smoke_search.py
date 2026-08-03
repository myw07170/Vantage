"""Phase 1 gate: does every configured search provider return the contract shape?

Runs the same query through each provider individually, then through the
failover chain, and validates the normalized result keys.

    uv run python scripts/smoke_search.py
    uv run python scripts/smoke_search.py "Notion vs Obsidian pricing"
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.core import search  # noqa: E402
from app.core.search import ddg, exa, tavily  # noqa: E402
from app.core.search.base import SearchUnavailable  # noqa: E402
from app.core.config import get_settings  # noqa: E402

REQUIRED_KEYS = {"title", "url", "snippet", "source", "captured_at"}


def check(provider, query: str) -> bool:
    label = provider.name
    if not provider.available():
        print(f"SKIP  {label:8s} no API key configured")
        return True
    try:
        results = provider.search(query, num=5)
    except SearchUnavailable as e:
        print(f"FAIL  {label:8s} unavailable: {e}")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"FAIL  {label:8s} raised {type(e).__name__}: {e}")
        return False

    if not results:
        print(f"WARN  {label:8s} returned 0 results (provider worked, found nothing)")
        return True

    missing = REQUIRED_KEYS - set(results[0].keys())
    if missing:
        print(f"FAIL  {label:8s} result is missing keys: {sorted(missing)}")
        return False

    with_content = sum(1 for r in results if r.get("content"))
    print(f"PASS  {label:8s} {len(results)} results, {with_content} with page content")
    print(f"      first: {results[0]['title'][:70]}")
    print(f"             {results[0]['url'][:70]}")
    return True


def main() -> int:
    query = sys.argv[1] if len(sys.argv) > 1 else "Notion vs Obsidian pricing comparison"
    settings = get_settings()
    print(f"query: {query!r}")
    print(f"chain: {settings.search_provider_chain}")
    print()

    ok = True
    for provider in (exa, tavily, ddg):
        ok &= check(provider, query)
        print()

    # The chain itself, including relevance filtering.
    try:
        results = search.search(query, num=6)
        print(f"PASS  chain    {len(results)} results after relevance filtering")
        for r in results[:3]:
            print(f"      - {r['title'][:64]}")
    except Exception as e:  # noqa: BLE001
        print(f"FAIL  chain    raised {type(e).__name__}: {e}")
        ok = False

    print()
    print("provider status:", search.provider_status())
    print()
    print("SMOKE PASSED" if ok else "SMOKE FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
