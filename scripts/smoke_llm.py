"""Check the selected LLM provider (mock needs no key or model network).

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
        print(f"FAIL  {settings.llm_configuration_error}")
        return 1

    print(f"provider: {settings.llm_provider}")
    print(f"core model: {settings.llm_model_core}")
    print(f"fast model: {settings.llm_model_fast}")
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
            task_kind="echo",
            mock_context={"text": "Paris"},
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
            task_kind="json",
            mock_context={"result": {"companies": [
                {"name": "Asana", "category": "Project management"},
                {"name": "Monday.com", "category": "Project management"},
            ]}},
        )
        ok = isinstance(data, dict) and isinstance(data.get("companies"), list) and len(data["companies"]) >= 1
        print(f"{'PASS' if ok else 'FAIL'}  chat_json() -> {data}")
        failures += 0 if ok else 1
    except Exception as e:
        print(f"FAIL  chat_json() raised: {type(e).__name__}: {e}")
        failures += 1

    # 3. Fast model reachable (same model shares the core bucket).
    try:
        out = llm.chat(
            [{"role": "user", "content": "Reply with the single word: ok"}],
            model=settings.llm_model_fast,
            max_tokens=16,
            temperature=0.0,
            task_kind="echo",
            mock_context={"text": "ok"},
        )
        tier = llm.tier_for(settings.llm_model_fast)
        ok = out.strip().lower() == "ok"
        print(f"{'PASS' if ok else 'FAIL'}  fast model -> {out.strip()!r} (tier={tier})")
        failures += 0 if ok else 1
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
