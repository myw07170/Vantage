"""Phase 1 gate: is Gemini's free tier actually usable for this pipeline?

This is the decisive test. The pipeline fans out up to 12 concurrent section
writes; the free tier allows roughly 10 requests/minute. If the rate limiter
works, a burst is paced smoothly and nothing 429s. If it does not, this fails
loudly here rather than halfway through a research run.

    uv run python scripts/soak_llm.py
    uv run python scripts/soak_llm.py 24     # burst size

Passing means: zero unretried 429s, and observed RPM at or under the configured
cap. A slow run is fine — being throttled is the point.
"""
from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.core import llm  # noqa: E402
from app.core.config import get_settings  # noqa: E402

_results: list[tuple[int, float, str | None]] = []
_lock = threading.Lock()


def worker(i: int, start: float) -> None:
    t0 = time.monotonic()
    err: str | None = None
    try:
        llm.chat(
            [{"role": "user", "content": f"Reply with only this number: {i}"}],
            max_tokens=16,
            temperature=0.0,
        )
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    with _lock:
        _results.append((i, time.monotonic() - start, err))


def main() -> int:
    burst = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    settings = get_settings()
    if not settings.llm_configured:
        print("FAIL  GEMINI_API_KEY is not set")
        return 1

    rpm = settings.gemini_rpm_core
    print(f"model:       {settings.gemini_model_core}")
    print(f"burst size:  {burst} concurrent calls")
    print(f"configured:  {rpm} rpm, max concurrency {settings.gemini_max_concurrency}")
    expected = max(0.0, (burst - rpm) / max(rpm, 1) * 60.0)
    print(f"expect this to take roughly {expected:.0f}s if throttling works\n")

    start = time.monotonic()
    threads = [threading.Thread(target=worker, args=(i, start)) for i in range(burst)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - start

    errors = [(i, e) for i, _, e in _results if e]
    rate_limited = [e for _, e in errors if "429" in e or "RESOURCE_EXHAUSTED" in e]

    print(f"completed {len(_results)} calls in {elapsed:.1f}s")
    print(f"observed rate: {len(_results) / max(elapsed, 1) * 60:.1f} requests/min")
    print(f"errors: {len(errors)} (of which rate-limit: {len(rate_limited)})")
    for i, e in errors[:5]:
        print(f"  call {i}: {e[:160]}")

    for tier, q in llm.quota_snapshot().items():
        print(
            f"  {tier}: {q['rpm_used']}/{q['rpm_limit']} rpm, "
            f"{q['rpd_used']}/{q['rpd_limit']} rpd"
        )

    ok = not rate_limited and len(errors) == 0
    print()
    if ok:
        print("SOAK PASSED — the free tier can drive the pipeline.")
    else:
        print("SOAK FAILED — lower GEMINI_RPM_CORE / GEMINI_MAX_CONCURRENCY in .env,")
        print("or check your real limits at https://aistudio.google.com/rate-limit")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
