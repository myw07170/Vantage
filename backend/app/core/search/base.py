"""Search provider contract.

Every provider normalizes to the same result shape so the pipeline never knows
which backend served a query:

    {title, url, snippet, source, captured_at, content?}

`content` is optional — providers that already return cleaned page text (Tavily,
Exa) populate it, which lets the collector skip a fetch round-trip.
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional, Protocol, runtime_checkable


class Freshness:
    """Provider-agnostic recency filter."""

    ANY = "any"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"

    _DAYS = {ANY: 0, DAY: 1, WEEK: 7, MONTH: 30, YEAR: 365}

    @classmethod
    def to_days(cls, freshness: str) -> int:
        return cls._DAYS.get(freshness or cls.ANY, 0)

    @classmethod
    def to_start_date(cls, freshness: str) -> Optional[str]:
        """ISO-8601 lower bound, or None for no limit."""
        days = cls.to_days(freshness)
        if days <= 0:
            return None
        start = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
        return start.strftime("%Y-%m-%dT%H:%M:%SZ")


class SearchUnavailable(RuntimeError):
    """This provider cannot serve the request — the chain should fail over.

    Raised for missing keys, auth failures, quota exhaustion and 5xx. An empty
    result set is *not* an error: it means the provider worked and found
    nothing, so failing over would just waste another provider's quota.
    """


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@runtime_checkable
class SearchProvider(Protocol):
    name: str

    def available(self) -> bool:
        """False when the provider has no key configured."""
        ...

    def search(
        self,
        query: str,
        *,
        num: int = 10,
        site: Optional[str] = None,
        freshness: str = Freshness.ANY,
    ) -> list[dict]:
        """Return normalized results, or raise SearchUnavailable to fail over."""
        ...
