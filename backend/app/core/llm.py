"""Provider-neutral completions, JSON parsing, local quotas and tracing.

Real providers use the OpenAI-compatible HTTP adapter. Mock calls use explicit
task kinds and structured context, never a model API or a quota lease.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import threading
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import httpx

from app.core import llm_mock, ratelimit, trace
from app.core.config import get_settings

TIER_CORE = "core"
TIER_FAST = "fast"


class LLMNotConfigured(RuntimeError):
    """The selected real provider has no API key."""


class LLMResponseError(RuntimeError):
    """The provider returned no usable completion or refused the request."""


DailyQuotaExhausted = ratelimit.DailyQuotaExhausted


def raise_if_fatal(error: Exception) -> None:
    """Fallbacks may repair malformed output, never hide auth or quota failure."""
    if isinstance(error, (LLMNotConfigured, DailyQuotaExhausted)):
        raise error
    if isinstance(error, httpx.HTTPStatusError) and error.response.status_code in (401, 403, 429):
        raise error


_client: httpx.Client | None = None
_client_lock = threading.Lock()
_limiter_ready = False
TOKEN_USAGE = {"total": 0}
_usage_lock = threading.Lock()


@dataclass
class _Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


def _get_client() -> httpx.Client:
    global _client
    settings = get_settings()
    if not settings.llm_configured:
        raise LLMNotConfigured(settings.llm_configuration_error)
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = httpx.Client(timeout=settings.llm_timeout)
    return _client


def _ensure_limiter() -> None:
    global _limiter_ready
    s = get_settings()
    if s.is_mock or _limiter_ready:
        return
    with _client_lock:
        if _limiter_ready:
            return
        tiers = [TIER_CORE]
        if s.llm_model_fast != s.llm_model_core:
            tiers.append(TIER_FAST)
        for tier in tiers:
            ratelimit.limiter.configure(
                tier, rpm=getattr(s, f"llm_rpm_{tier}"),
                rpd=getattr(s, f"llm_rpd_{tier}"),
                tpm=getattr(s, f"llm_tpm_{tier}"),
                max_concurrency=s.llm_max_concurrency,
            )
        _limiter_ready = True


def tier_for(model: str) -> str:
    s = get_settings()
    if model == s.llm_model_fast and s.llm_model_fast != s.llm_model_core:
        return TIER_FAST
    return TIER_CORE


def _retry_after(err: Exception) -> Optional[float]:
    if not isinstance(err, httpx.HTTPStatusError):
        return None
    value = err.response.headers.get("Retry-After", "")
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=dt.timezone.utc)
            return max(0.0, (when - dt.datetime.now(dt.timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


def _is_retryable(err: Exception) -> bool:
    if isinstance(err, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    return isinstance(err, httpx.HTTPStatusError) and err.response.status_code in (
        408, 429, 500, 502, 503, 504,
    )


def _request_messages(messages: list[dict], json_mode: bool, schema: Any) -> list[dict]:
    # Copy before appending instructions; callers can reuse their message list.
    out = [dict(m) for m in messages]
    if not out:
        out = [{"role": "user", "content": "Hello"}]
    if json_mode:
        instruction = (
            'Return valid JSON only, as a JSON object. If the requested result '
            'is an array, wrap it as {"items": [...]}.'
        )
        if schema is not None:
            shape = schema.model_json_schema() if hasattr(schema, "model_json_schema") else schema
            instruction += " Follow this JSON schema for the requested result: " + json.dumps(shape)
        out.insert(0, {"role": "system", "content": instruction})
    return out


def _complete_http(client: httpx.Client, messages: list[dict], model: str,
                   temperature: float, max_tokens: int, json_mode: bool) -> tuple[str, _Usage | None]:
    s = get_settings()
    payload = {"model": model, "messages": messages, "temperature": temperature, "stream": False}
    if s.llm_provider == "qwen":
        payload.update(max_tokens=max_tokens, enable_thinking=False)
    else:
        payload["max_completion_tokens"] = max_tokens
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    response = client.post(
        s.llm_base_url.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {s.llm_api_key}"}, json=payload,
    )
    response.raise_for_status()
    try:
        data = response.json()
        choice = data["choices"][0]
        message = choice["message"]
        if not isinstance(choice, dict) or not isinstance(message, dict):
            raise LLMResponseError("The LLM provider returned a malformed completion.")
        refused = message.get("refusal") or choice.get("finish_reason") == "content_filter"
        content = message.get("content")
        if refused:
            raise LLMResponseError("The LLM provider refused the request.")
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError("The LLM provider returned an empty completion.")
        usage = None
        if isinstance(data.get("usage"), dict):
            um = data["usage"]
            pt = int(um.get("prompt_tokens") or 0)
            ct = int(um.get("completion_tokens") or 0)
            usage = _Usage(pt, ct, int(um.get("total_tokens") or pt + ct))
        return content.strip(), usage
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise LLMResponseError("The LLM provider returned a malformed completion.") from e


def _record(model, messages, content, usage, latency_ms, purpose, evidence_ids):
    try:
        trace.record_span(
            model=model, messages=messages, response=content, usage=usage,
            latency_ms=latency_ms, decision=purpose, evidence_ids=evidence_ids,
        )
    except Exception:
        pass


def chat(
    messages: list[dict], temperature: float = 0.6, max_tokens: int = 2048,
    model: str | None = None, *, purpose: str = "",
    evidence_ids: Optional[list] = None, response_mime_type: Optional[str] = None,
    response_schema: Optional[Any] = None, task_kind: str = "",
    mock_context: dict | None = None,
) -> str:
    """Return text, keeping provider transport, quotas and tracing in one layer."""
    s = get_settings()
    use_model = model or s.llm_model_core
    json_mode = response_mime_type == "application/json"
    wire_messages = _request_messages(messages, json_mode, response_schema)
    if s.is_mock:
        t0 = time.perf_counter()
        content = llm_mock.complete(messages, task_kind, mock_context or {}, json_mode)
        _record(f"mock:{use_model}", messages, content, _Usage(),
                int((time.perf_counter() - t0) * 1000), purpose, evidence_ids)
        return content

    client = _get_client()
    _ensure_limiter()
    tier = tier_for(use_model)
    est = ratelimit.estimate_tokens(wire_messages, max_tokens)
    for attempt in range(s.llm_max_retries + 1):
        with ratelimit.slot(ratelimit.limiter, tier, est) as lease:
            try:
                t0 = time.perf_counter()
                content, usage = _complete_http(client, wire_messages, use_model, temperature, max_tokens, json_mode)
                latency = int((time.perf_counter() - t0) * 1000)
                if usage is not None:
                    with _usage_lock:
                        TOKEN_USAGE["total"] += usage.total_tokens
                    lease.reconcile(usage.total_tokens)
                _record(use_model, messages, content, usage, latency, purpose, evidence_ids)
                return content
            except Exception as e:
                if not _is_retryable(e) or attempt >= s.llm_max_retries:
                    raise
                delay = ratelimit.backoff_delay(attempt, _retry_after(e))
        time.sleep(delay)
    raise AssertionError("unreachable")


def chat_json(
    messages: list[dict], temperature: float = 0.3, max_tokens: int = 2048,
    model: str | None = None, *, purpose: str = "", schema: Optional[Any] = None,
    task_kind: str = "", mock_context: dict | None = None,
) -> Optional[Any]:
    """Parse JSON, returning None for unparseable output; transport errors raise."""
    raw = chat(
        messages, temperature=temperature, max_tokens=max_tokens, model=model,
        purpose=purpose, response_mime_type="application/json", response_schema=schema,
        task_kind=task_kind, mock_context=mock_context,
    )
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        data = _extract_json(raw)
    if isinstance(data, dict) and set(data) == {"items"} and isinstance(data["items"], list):
        return data["items"]
    return data


def chat_schema(
    messages: list[dict], coerce, *, temperature: float = 0.3,
    max_tokens: int = 4096, model: str | None = None, purpose: str = "",
    schema: Optional[Any] = None, task_kind: str = "", mock_context: dict | None = None,
):
    """Apply the caller's tolerant coercion after JSON parsing."""
    raw = chat_json(
        messages, temperature=temperature, max_tokens=max_tokens, model=model,
        purpose=purpose, schema=schema, task_kind=task_kind, mock_context=mock_context,
    )
    try:
        return coerce(raw)
    except Exception:
        return None


def _extract_json(text: str) -> Optional[Any]:
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except ValueError:
        pass
    for pat in (r"\[.*\]", r"\{.*\}"):
        m = re.search(pat, text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                continue
    return None


def quota_snapshot() -> dict:
    if get_settings().is_mock:
        return {}
    _ensure_limiter()
    return ratelimit.limiter.snapshot()
