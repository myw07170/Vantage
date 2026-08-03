"""Phase 1 gate: is the Gemini layer wired up correctly?

Checks a plain completion, native JSON mode, tier routing and the quota
snapshot. Run this before touching anything that depends on the LLM.

    uv run python scripts/smoke_llm.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.core import llm  # noqa: E402
from app.core.config import get_settings  # noqa: E402


def main() -> int:
    settings = get_settings()
    if not settings.llm_configured:
        print("FAIL  GEMINI_API_KEY is not set — copy backend/.env.example to backend/.env")
        return 1

    print(f"core model: {settings.gemini_model_core}")
    print(f"fast model: {settings.gemini_model_fast}")
    print()

    failures = 0

    # 1. Plain text completion on the core model.
    try:
        out = llm.chat(
            [
                {"role": "system", "content": "Answer in exactly one word."},
                {"role": "user", "content": "What is the capital of France?"},
            ],
            max_tokens=32,
            temperature=0.0,
        )
        ok = "paris" in out.lower()
        print(f"{'PASS' if ok else 'FAIL'}  chat() -> {out!r}")
        failures += 0 if ok else 1
    except Exception as e:
        print(f"FAIL  chat() raised: {type(e).__name__}: {e}")
        failures += 1

    # 2. Native JSON mode — must parse without the regex fallback.
    try:
        data = llm.chat_json(
            [
                {
                    "role": "system",
                    "content": "Return JSON shaped {\"companies\": [{\"name\": str, \"category\": str}]}.",
                },
                {"role": "user", "content": "List exactly 2 US project-management SaaS companies."},
            ],
            max_tokens=256,
        )
        ok = isinstance(data, dict) and isinstance(data.get("companies"), list) and len(data["companies"]) >= 1
        print(f"{'PASS' if ok else 'FAIL'}  chat_json() -> {data}")
        failures += 0 if ok else 1
    except Exception as e:
        print(f"FAIL  chat_json() raised: {type(e).__name__}: {e}")
        failures += 1

    # 3. Fast tier reachable and routed to its own bucket.
    try:
        out = llm.chat(
            [{"role": "user", "content": "Reply with the single word: ok"}],
            model=settings.gemini_model_fast,
            max_tokens=16,
            temperature=0.0,
        )
        tier = llm.tier_for(settings.gemini_model_fast)
        print(f"PASS  fast model -> {out.strip()!r} (tier={tier})")
    except Exception as e:
        print(f"FAIL  fast model raised: {type(e).__name__}: {e}")
        failures += 1

    print()
    print(f"tokens used this run: {llm.TOKEN_USAGE['total']}")
    for tier, q in llm.quota_snapshot().items():
        print(
            f"  {tier}: {q['rpm_used']}/{q['rpm_limit']} rpm, "
            f"{q['rpd_used']}/{q['rpd_limit']} rpd "
            f"({q['rpd_remaining']} left today)"
        )

    print()
    print("SMOKE PASSED" if failures == 0 else f"SMOKE FAILED ({failures} check(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
