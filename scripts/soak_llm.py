"""Concurrent completions against the selected LLM provider.

Mock exercises concurrent local calls. Real calls use configured local budgets;
set LLM_RPM_CORE to a positive cap to exercise pacing.

    uv run python scripts/soak_llm.py
    uv run python scripts/soak_llm.py 24     # burst size

Passing means every concurrent completion succeeds without unretried 429s.
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
            task_kind="echo",
            mock_context={"text": str(i)},
        )
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    with _lock:
        _results.append((i, time.monotonic() - start, err))


def main() -> int:
    burst = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    settings = get_settings()
    if not settings.llm_configured:
        print(f"FAIL  {settings.llm_configuration_error}")
        return 1

    rpm = settings.llm_rpm_core
    print(f"provider: {settings.llm_provider}")
    print(f"model:       {settings.llm_model_core}")
    print(f"burst size:  {burst} concurrent calls")
    print(f"configured:  {rpm} rpm, max concurrency {settings.llm_max_concurrency}")
    expected = max(0.0, (burst - rpm) / rpm * 60.0) if rpm > 0 and not settings.is_mock else 0.0
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
        print("SOAK PASSED — all concurrent completions succeeded.")
    else:
        print("SOAK FAILED — check provider access and limits; set LLM_RPM_CORE /")
        print("LLM_MAX_CONCURRENCY in backend/.env to fit your actual account quota.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
