"""Thread-safe token-bucket rate limiting for Gemini's free tier.

Why this module exists
----------------------
The pipeline fans out up to 12 concurrent section writes (see orchestrator's
parallel write stage), and every LLM call runs inside an `asyncio.to_thread`
worker. Gemini's free tier allows roughly 10 requests/minute on Flash. Firing
the fan-out unthrottled means almost every request 429s, and blind retry storms
make it worse.

So the limiter must be:

* **thread-safe, not asyncio-safe** — callers are OS threads, not coroutines,
  so this uses `threading.Lock`/`Condition` rather than asyncio primitives.
* **multi-dimensional** — Gemini enforces requests/minute, requests/day and
  tokens/minute independently. Exceeding any one of them 429s.
* **fair** — waiters wake in arrival order, so a burst of section writes does
  not starve the intake call that unblocks the next stage.

`acquire()` blocks until every bucket has capacity, then records the spend.
Daily counters reset at midnight Pacific, matching Google's quota reset.
"""
from __future__ import annotations

import datetime as _dt
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

# Google resets free-tier daily quotas at midnight Pacific.
_PACIFIC = _dt.timezone(_dt.timedelta(hours=-8))


def _pacific_day() -> str:
    return _dt.datetime.now(_PACIFIC).strftime("%Y-%m-%d")


@dataclass
class _Window:
    """A sliding 60-second counter.

    Timestamps of recent spends are kept so capacity frees up continuously
    instead of in a sawtooth at each minute boundary — which matters because
    Gemini itself measures over a rolling window.
    """

    limit: int
    events: list[tuple[float, int]] = field(default_factory=list)

    def _trim(self, now: float) -> None:
        cutoff = now - 60.0
        # Events are appended in time order, so dropping from the front is enough.
        idx = 0
        for ts, _ in self.events:
            if ts > cutoff:
                break
            idx += 1
        if idx:
            del self.events[:idx]

    def used(self, now: float) -> int:
        self._trim(now)
        return sum(n for _, n in self.events)

    def has_room(self, now: float, cost: int) -> bool:
        if self.limit <= 0:
            return True
        # A single request larger than the whole window can never fit; let it
        # through rather than deadlock, and let the API be the judge.
        if cost > self.limit:
            return not self.events
        return self.used(now) + cost <= self.limit

    def spend(self, now: float, cost: int) -> None:
        self.events.append((now, cost))

    def retry_after(self, now: float, cost: int) -> float:
        """Seconds until the oldest event ages out and frees capacity."""
        self._trim(now)
        if not self.events:
            return 0.05
        oldest = self.events[0][0]
        return max(0.05, (oldest + 60.0) - now)


@dataclass
class _Bucket:
    """All quota dimensions for one model tier."""

    name: str
    rpm: _Window
    tpm: _Window
    rpd_limit: int
    rpd_used: int = 0
    rpd_day: str = field(default_factory=_pacific_day)

    def _roll_day(self) -> None:
        today = _pacific_day()
        if today != self.rpd_day:
            self.rpd_day = today
            self.rpd_used = 0

    def daily_remaining(self) -> int:
        self._roll_day()
        if self.rpd_limit <= 0:
            return -1  # unlimited
        return max(0, self.rpd_limit - self.rpd_used)


class DailyQuotaExhausted(RuntimeError):
    """The per-day request budget for a model tier is spent.

    Raised rather than blocked on, because waiting for a daily reset would hang
    a request for hours. Callers should surface this to the user.
    """


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._buckets: Dict[str, _Bucket] = {}
        self._sem: Optional[threading.Semaphore] = None
        self._max_concurrency = 0
        self._ticket = 0  # monotonic arrival counter, for FIFO fairness
        self._serving = 0

    # ---- configuration ------------------------------------------------------

    def configure(
        self,
        tier: str,
        *,
        rpm: int,
        rpd: int,
        tpm: int,
        max_concurrency: int,
    ) -> None:
        with self._lock:
            self._buckets[tier] = _Bucket(
                name=tier,
                rpm=_Window(limit=rpm),
                tpm=_Window(limit=tpm),
                rpd_limit=rpd,
            )
            if self._sem is None or max_concurrency != self._max_concurrency:
                self._max_concurrency = max_concurrency
                self._sem = threading.Semaphore(max_concurrency)

    # ---- acquire / release --------------------------------------------------

    def acquire(self, tier: str, est_tokens: int = 0) -> None:
        """Block until `tier` has room for one request of `est_tokens`.

        Pairs with `release()`; use the `slot()` context manager instead of
        calling these directly.
        """
        sem = self._sem
        if sem is not None:
            sem.acquire()
        try:
            with self._cond:
                bucket = self._buckets.get(tier)
                if bucket is None:
                    return
                self._ticket += 1
                my_turn = self._ticket
                while True:
                    now = time.monotonic()
                    bucket._roll_day()
                    if bucket.rpd_limit > 0 and bucket.rpd_used >= bucket.rpd_limit:
                        raise DailyQuotaExhausted(
                            f"Daily request quota for '{tier}' is exhausted "
                            f"({bucket.rpd_used}/{bucket.rpd_limit}). "
                            "It resets at midnight US/Pacific."
                        )
                    ahead = my_turn > self._serving + 1
                    fits = bucket.rpm.has_room(now, 1) and bucket.tpm.has_room(
                        now, max(0, est_tokens)
                    )
                    if fits and not ahead:
                        bucket.rpm.spend(now, 1)
                        if est_tokens > 0:
                            bucket.tpm.spend(now, est_tokens)
                        bucket.rpd_used += 1
                        self._serving = my_turn
                        return
                    wait = min(
                        bucket.rpm.retry_after(now, 1),
                        bucket.tpm.retry_after(now, max(1, est_tokens)),
                    )
                    self._cond.wait(timeout=max(0.05, min(wait, 5.0)))
        except BaseException:
            # Never leak the concurrency slot if we raise before returning.
            if sem is not None:
                sem.release()
            raise

    def release(self) -> None:
        sem = self._sem
        if sem is not None:
            sem.release()
        with self._cond:
            self._cond.notify_all()

    def record_actual_tokens(self, tier: str, actual: int, estimated: int) -> None:
        """Reconcile the TPM window once real usage is known.

        Estimates are deliberately rough; this corrects the difference so a
        systematically low estimate cannot silently overrun the token budget.
        """
        delta = actual - estimated
        if delta == 0:
            return
        with self._cond:
            bucket = self._buckets.get(tier)
            if bucket is None:
                return
            bucket.tpm.spend(time.monotonic(), delta)
            self._cond.notify_all()

    # ---- introspection ------------------------------------------------------

    def snapshot(self) -> dict:
        """Current usage per tier — surfaced by /api/llm/ping."""
        now = time.monotonic()
        with self._lock:
            return {
                tier: {
                    "rpm_limit": b.rpm.limit,
                    "rpm_used": b.rpm.used(now),
                    "tpm_limit": b.tpm.limit,
                    "tpm_used": b.tpm.used(now),
                    "rpd_limit": b.rpd_limit,
                    "rpd_used": b.rpd_used,
                    "rpd_remaining": b.daily_remaining(),
                }
                for tier, b in self._buckets.items()
            }


class slot:
    """Context manager pairing `acquire`/`release` around one request."""

    def __init__(self, limiter: RateLimiter, tier: str, est_tokens: int = 0):
        self._limiter = limiter
        self._tier = tier
        self._est = est_tokens

    def __enter__(self) -> "slot":
        self._limiter.acquire(self._tier, self._est)
        return self

    def __exit__(self, *exc) -> None:
        self._limiter.release()

    def reconcile(self, actual_tokens: int) -> None:
        self._limiter.record_actual_tokens(self._tier, actual_tokens, self._est)


# Module-level singleton; configured once by llm.py on first use.
limiter = RateLimiter()


def backoff_delay(attempt: int, retry_after: Optional[float] = None) -> float:
    """Delay before retry `attempt` (0-based).

    Honors the server's own `retryDelay` when Gemini sends one, otherwise
    exponential backoff with jitter to avoid a thundering herd after a burst.
    """
    if retry_after is not None and retry_after > 0:
        return min(retry_after + random.uniform(0, 0.5), 60.0)
    base = min(2.0 * (2**attempt), 32.0)
    return base * (0.5 + random.random())


def estimate_tokens(messages: list[dict], max_output: int) -> int:
    """Rough token estimate for TPM accounting.

    ~4 characters per token is the usual English approximation. Output is
    counted at its ceiling since the real length is unknown up front; the
    actual figure is reconciled after the call via `slot.reconcile`.
    """
    chars = sum(len(str(m.get("content", ""))) for m in messages)
    return int(chars / 4) + max_output
