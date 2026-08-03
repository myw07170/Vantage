"""Google Gemini client wrapper.

Public surface is deliberately small and provider-agnostic — `chat()`,
`chat_json()`, `chat_schema()` — so the orchestrator's ~40 call sites never
touch the SDK directly.

Three things this layer is responsible for:

1. **Rate limiting.** Every call passes through `ratelimit.limiter` before it
   reaches the network. Gemini's free tier is ~10 RPM on Flash while the
   pipeline fans out up to 12 concurrent section writes, so this is what makes
   the free tier usable at all.
2. **Guaranteed JSON.** `chat_json` uses Gemini's native
   `response_mime_type="application/json"` instead of scraping JSON out of
   prose. Regex extraction remains only as a defensive fallback.
3. **Tracing.** Every call records a span via `trace.record_span()`, picking up
   the agent/stage from the ambient contextvar.

Keys come from the environment only; nothing is hardcoded.
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core import ratelimit, trace
from app.core.config import get_settings

# Model tier names, used as rate-limit bucket keys.
TIER_CORE = "core"
TIER_FAST = "fast"


class LLMNotConfigured(RuntimeError):
    """GEMINI_API_KEY is not set."""


# Re-exported so callers can handle quota exhaustion without importing ratelimit.
DailyQuotaExhausted = ratelimit.DailyQuotaExhausted

_client: genai.Client | None = None
_client_lock = threading.Lock()
_limiter_ready = False

# Process-wide token counter, used for live progress reporting.
TOKEN_USAGE = {"total": 0}
_usage_lock = threading.Lock()


@dataclass
class _Usage:
    """Provider usage normalized to the field names trace.py expects."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


def _get_client() -> genai.Client:
    global _client
    settings = get_settings()
    if not settings.gemini_api_key:
        raise LLMNotConfigured(
            "GEMINI_API_KEY is not set. Add it to backend/.env — get a key at "
            "https://aistudio.google.com/apikey"
        )
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = genai.Client(
                    api_key=settings.gemini_api_key,
                    http_options=types.HttpOptions(
                        timeout=int(settings.llm_timeout * 1000)  # milliseconds
                    ),
                )
    return _client


def _ensure_limiter() -> None:
    """Configure the rate-limit buckets from settings, once per process."""
    global _limiter_ready
    if _limiter_ready:
        return
    with _client_lock:
        if _limiter_ready:
            return
        s = get_settings()
        ratelimit.limiter.configure(
            TIER_CORE,
            rpm=s.gemini_rpm_core,
            rpd=s.gemini_rpd_core,
            tpm=s.gemini_tpm_core,
            max_concurrency=s.gemini_max_concurrency,
        )
        ratelimit.limiter.configure(
            TIER_FAST,
            rpm=s.gemini_rpm_fast,
            rpd=s.gemini_rpd_fast,
            tpm=s.gemini_tpm_fast,
            max_concurrency=s.gemini_max_concurrency,
        )
        _limiter_ready = True


def tier_for(model: str) -> str:
    """Which quota bucket a model name draws from.

    Gemini meters per model, so the fast tier only gets its own budget when it
    is genuinely a different model from the core one.
    """
    s = get_settings()
    if model == s.gemini_model_fast and s.gemini_model_fast != s.gemini_model_core:
        return TIER_FAST
    return TIER_CORE


def _thinking_config(model: str) -> Optional[types.ThinkingConfig]:
    """Minimize deliberation — this pipeline wants fast, stable output.

    Gemini 3.x models take a categorical `thinking_level`; the 2.5 generation
    takes a numeric `thinking_budget`. Returns None when neither applies.
    """
    budget = get_settings().gemini_thinking_budget
    m = model.lower()
    if "gemini-3" in m:
        return types.ThinkingConfig(thinking_level="low")
    if "gemini-2.5" in m or "gemini-2-5" in m:
        return types.ThinkingConfig(thinking_budget=max(0, budget))
    return None


def _to_contents(messages: list[dict]) -> tuple[str, list[types.Content]]:
    """Convert OpenAI-style messages into (system_instruction, contents).

    Gemini takes the system prompt out-of-band and uses the role name "model"
    where OpenAI uses "assistant".
    """
    system_parts: list[str] = []
    contents: list[types.Content] = []
    for m in messages:
        role = (m.get("role") or "user").lower()
        text = str(m.get("content") or "")
        if not text:
            continue
        if role == "system":
            system_parts.append(text)
            continue
        gem_role = "model" if role in ("assistant", "model") else "user"
        contents.append(
            types.Content(role=gem_role, parts=[types.Part.from_text(text=text)])
        )
    if not contents:
        # Gemini rejects an empty conversation; fall back to the system text.
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text="\n\n".join(system_parts) or "Hello")],
            )
        ]
        system_parts = []
    return "\n\n".join(system_parts), contents


def _status_code(err: Exception) -> Optional[int]:
    code = getattr(err, "code", None)
    if isinstance(code, int):
        return code
    status = str(getattr(err, "status", "") or "")
    if status.isdigit():
        return int(status)
    m = re.search(r"\b(4\d\d|5\d\d)\b", str(err))
    return int(m.group(1)) if m else None


def _retry_after(err: Exception) -> Optional[float]:
    """Gemini's own suggested delay, when it sends RetryInfo."""
    m = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", str(err))
    return float(m.group(1)) if m else None


def _is_retryable(err: Exception) -> bool:
    code = _status_code(err)
    if code in (408, 429, 500, 502, 503, 504):
        return True
    if isinstance(err, genai_errors.ServerError):
        return True
    text = str(err).lower()
    return "timeout" in text or "deadline" in text or "unavailable" in text


def _rejects_thinking(err: Exception) -> bool:
    """The model refused the thinking config — retry once without it."""
    if _status_code(err) != 400:
        return False
    text = str(err).lower()
    return "thinking" in text or "thought" in text


def chat(
    messages: list[dict],
    temperature: float = 0.6,
    max_tokens: int = 2048,
    model: str | None = None,
    *,
    purpose: str = "",
    evidence_ids: Optional[list] = None,
    response_mime_type: Optional[str] = None,
    response_schema: Optional[Any] = None,
) -> str:
    """One completion, returned as text. Blocks on the rate limiter first.

    Args:
        model: overrides the configured default (used for tier routing).
        purpose/evidence_ids: attached to the trace span for decision replay.
        response_mime_type/response_schema: set by `chat_json` for native
            structured output; callers normally leave these alone.
    """
    settings = get_settings()
    client = _get_client()
    _ensure_limiter()

    use_model = model or settings.gemini_model_core
    tier = tier_for(use_model)
    system_instruction, contents = _to_contents(messages)
    thinking = _thinking_config(use_model)
    est = ratelimit.estimate_tokens(messages, max_tokens)

    last_err: Exception | None = None
    for attempt in range(settings.llm_max_retries + 1):
        with ratelimit.slot(ratelimit.limiter, tier, est) as lease:
            try:
                config = types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    system_instruction=system_instruction or None,
                    thinking_config=thinking,
                    response_mime_type=response_mime_type,
                    response_schema=response_schema,
                )
                t0 = time.perf_counter()
                resp = client.models.generate_content(
                    model=use_model, contents=contents, config=config
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                content = (resp.text or "").strip()

                usage = _Usage()
                um = getattr(resp, "usage_metadata", None)
                if um is not None:
                    usage = _Usage(
                        prompt_tokens=int(getattr(um, "prompt_token_count", 0) or 0),
                        completion_tokens=int(
                            getattr(um, "candidates_token_count", 0) or 0
                        ),
                        total_tokens=int(getattr(um, "total_token_count", 0) or 0),
                    )
                    with _usage_lock:
                        TOKEN_USAGE["total"] += usage.total_tokens
                    lease.reconcile(usage.total_tokens)

                try:
                    trace.record_span(
                        model=use_model,
                        messages=messages,
                        response=content,
                        usage=usage,
                        latency_ms=latency_ms,
                        decision=purpose,
                        evidence_ids=evidence_ids,
                    )
                except Exception:
                    pass
                return content

            except Exception as e:  # noqa: BLE001
                last_err = e
                if _rejects_thinking(e) and thinking is not None:
                    thinking = None
                    continue
                if not _is_retryable(e) or attempt >= settings.llm_max_retries:
                    raise
        # Sleep outside the lease so a backing-off call does not hold a slot.
        time.sleep(ratelimit.backoff_delay(attempt, _retry_after(last_err)))

    assert last_err is not None
    raise last_err


def chat_json(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2048,
    model: str | None = None,
    *,
    purpose: str = "",
    schema: Optional[Any] = None,
) -> Optional[Any]:
    """Ask for JSON and parse it. Returns None on failure; caller decides.

    Uses Gemini's native JSON mode, so the response is valid JSON by
    construction. `_extract_json` only matters if a future model ignores the
    mime type or the output is truncated by `max_tokens`.
    """
    raw = chat(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        model=model,
        purpose=purpose,
        response_mime_type="application/json",
        response_schema=schema,
    )
    try:
        return json.loads(raw)
    except Exception:
        return _extract_json(raw)


def chat_schema(
    messages: list[dict],
    coerce,
    *,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    model: str | None = None,
    purpose: str = "",
    schema: Optional[Any] = None,
):
    """Structured output: JSON in, then `coerce` into the target shape.

    `coerce` is one of the tolerant `coerce_*` functions in schemas.py — it
    drops invalid fields rather than raising, so a partially-good response
    still yields usable structure.
    """
    raw = chat_json(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        model=model,
        purpose=purpose,
        schema=schema,
    )
    try:
        return coerce(raw)
    except Exception:
        return None


def _extract_json(text: str) -> Optional[Any]:
    """Defensive fallback: pull JSON out of prose or a fenced block."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except Exception:
        pass
    for pat in (r"\[.*\]", r"\{.*\}"):
        m = re.search(pat, text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                continue
    return None


def quota_snapshot() -> dict:
    """Live rate-limit usage per tier, surfaced by /api/llm/ping."""
    _ensure_limiter()
    return ratelimit.limiter.snapshot()
