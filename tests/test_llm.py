"""Provider contracts and failures without keys or network access."""
from __future__ import annotations

import datetime as dt
import json
from email.utils import format_datetime

import httpx
import pytest
from pydantic import ValidationError

from app.core import llm, ratelimit
from app.core.config import Settings


@pytest.fixture
def runtime(monkeypatch):
    settings = Settings(_env_file=None, llm_provider="mock", openai_api_key="", qwen_api_key="",
                        dashscope_api_key="", llm_max_retries=2)
    spans = []
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm, "_limiter_ready", False)
    monkeypatch.setattr(llm, "TOKEN_USAGE", {"total": 0})
    monkeypatch.setattr(ratelimit, "limiter", ratelimit.RateLimiter())
    monkeypatch.setattr(llm.trace, "record_span", lambda **kw: spans.append(kw))
    yield settings, spans
    if llm._client is not None:
        llm._client.close()


def _transport(monkeypatch, handler):
    monkeypatch.setattr(llm, "_client", httpx.Client(transport=httpx.MockTransport(handler)))


def _response(content="ready", usage=None, **message):
    data = {"choices": [{"message": {"content": content, **message}, "finish_reason": "stop"}]}
    if usage is not None:
        data["usage"] = usage
    return httpx.Response(200, json=data)


def test_config_defaults_and_qwen_key_precedence(monkeypatch):
    for key in ("LLM_PROVIDER", "QWEN_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    default = Settings(_env_file=None)
    assert default.is_mock and default.llm_configured
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fallback")
    monkeypatch.setenv("QWEN_API_KEY", "primary")
    s = Settings(_env_file=None, llm_provider="qwen")
    assert s.llm_api_key == "primary"
    monkeypatch.delenv("QWEN_API_KEY")
    assert Settings(_env_file=None, llm_provider="qwen").llm_api_key == "fallback"
    assert Settings(_env_file=None, llm_provider="openai").llm_api_key == ""


@pytest.mark.parametrize("override", [{"llm_provider": "gemini"}, {"llm_rpm_core": -1},
                                     {"llm_max_concurrency": 0}, {"llm_max_retries": -1},
                                     {"llm_timeout": 0}])
def test_bad_configuration_rejected(override):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **override)


@pytest.mark.parametrize("provider", ["openai", "qwen"])
def test_missing_key_does_not_fall_back(runtime, provider):
    s, _ = runtime
    s.llm_provider = provider
    assert not s.llm_configured
    with pytest.raises(llm.LLMNotConfigured, match="API_KEY"):
        llm.chat([])


def test_mock_bypasses_http_quotas_and_records_zero_usage(runtime, monkeypatch):
    _, spans = runtime
    def forbidden(*args, **kwargs):
        pytest.fail("Mock must not acquire quotas or create an HTTP client")
    monkeypatch.setattr(llm, "_get_client", forbidden)
    monkeypatch.setattr(llm, "_ensure_limiter", forbidden)
    result = llm.chat([], task_kind="echo", mock_context={"text": "ready"})
    assert result == "ready" and llm.quota_snapshot() == {}
    assert spans[0]["model"].startswith("mock:")
    assert spans[0]["usage"].total_tokens == llm.TOKEN_USAGE["total"] == 0
    assert llm.chat_schema([], lambda raw: raw["value"], task_kind="json",
                           mock_context={"result": {"value": 4}}) == 4


@pytest.mark.parametrize("provider", ["openai", "qwen"])
def test_http_contract_json_arrays_schema_and_usage(runtime, monkeypatch, provider):
    s, spans = runtime
    s.llm_provider = provider
    s.openai_api_key = s.qwen_api_key = "test-key"
    s.openai_base_url = s.qwen_base_url = "https://example.test/custom/v1/"
    requests = []
    def handler(request):
        requests.append(request)
        return _response('{"items":[{"i":0,"s":"pos"}]}',
                         {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8})
    _transport(monkeypatch, handler)
    messages = [{"role": "user", "content": "Classify comments"}]
    schema = {"type": "array", "items": {"type": "object"}}
    assert llm.chat_json(messages, model="custom-model", max_tokens=100, schema=schema,
                         task_kind="sentiment", mock_context={"secret": "never sent"}) == [{"i": 0, "s": "pos"}]
    request = requests[0]
    body = json.loads(request.content)
    assert str(request.url) == "https://example.test/custom/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-key"
    assert body["model"] == "custom-model" and body["stream"] is False
    assert body["response_format"] == {"type": "json_object"}
    assert "JSON schema" in body["messages"][0]["content"]
    assert '"items"' in body["messages"][0]["content"]
    assert messages == [{"role": "user", "content": "Classify comments"}]
    assert "task_kind" not in body and "mock_context" not in body
    if provider == "qwen":
        assert body["max_tokens"] == 100 and body["enable_thinking"] is False
        assert "max_completion_tokens" not in body
    else:
        assert body["max_completion_tokens"] == 100
        assert "max_tokens" not in body and "enable_thinking" not in body
    assert llm.TOKEN_USAGE["total"] == spans[0]["usage"].total_tokens == 8
    assert llm.quota_snapshot()["core"]["tpm_used"] == 8


def test_same_model_shares_bucket_and_distinct_models_route(runtime):
    s, _ = runtime
    s.llm_provider = "qwen"
    assert llm.tier_for(s.llm_model_fast) == "core"
    assert set(llm.quota_snapshot()) == {"core"}
    s.qwen_model_fast = "other-model"
    llm._limiter_ready = False
    assert llm.tier_for(s.llm_model_fast) == "fast"
    assert set(llm.quota_snapshot()) == {"core", "fast"}


@pytest.mark.parametrize("content,expected", [('```json\n{"ok":true}\n```', {"ok": True}),
                                            ('[{"i":0}]', [{"i": 0}]), ("invalid", None)])
def test_json_fallback_and_missing_usage(runtime, monkeypatch, content, expected):
    s, spans = runtime
    s.llm_provider = "openai"
    s.openai_api_key = "test"
    _transport(monkeypatch, lambda request: _response(content))
    assert llm.chat_json([]) == expected
    assert spans[0]["usage"] is None and llm.TOKEN_USAGE["total"] == 0


@pytest.mark.parametrize("data", [
    {"choices": []}, {}, {"choices": [{"message": {"content": " "}}]},
    {"choices": [{"message": None}]}, {"choices": None},
    {"choices": [{"message": {"content": None, "refusal": "no"}}]},
    {"choices": [{"message": {"content": "blocked"}, "finish_reason": "content_filter"}]},
])
def test_bad_or_refused_completion_is_not_retried(runtime, monkeypatch, data):
    s, _ = runtime
    s.llm_provider = "openai"
    s.openai_api_key = "test"
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=data)
    _transport(monkeypatch, handler)
    with pytest.raises(llm.LLMResponseError):
        llm.chat([])
    assert len(requests) == 1


@pytest.mark.parametrize("failure", [408, 429, 500, 502, 503, 504, "timeout", "connection"])
def test_retry_and_lease_release(runtime, monkeypatch, failure):
    s, _ = runtime
    s.llm_provider = "openai"
    s.openai_api_key = "test"
    calls, delays = [], []
    def handler(request):
        calls.append(request)
        if len(calls) > 1:
            return _response()
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if failure == "connection":
            raise httpx.ConnectError("connection", request=request)
        return httpx.Response(failure, headers={"Retry-After": "2"})
    def sleep(delay):
        assert ratelimit.limiter._sem.acquire(blocking=False)
        ratelimit.limiter._sem.release()
        delays.append(delay)
    _transport(monkeypatch, handler)
    monkeypatch.setattr(llm.time, "sleep", sleep)
    assert llm.chat([]) == "ready" and len(calls) == 2
    assert len(delays) == 1
    if isinstance(failure, int):
        assert 2 <= delays[0] <= 2.5


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_nonretryable_http_errors(runtime, monkeypatch, status):
    s, _ = runtime
    s.llm_provider = "qwen"
    s.qwen_api_key = "test"
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status)
    _transport(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError):
        llm.chat([])
    assert len(requests) == 1 and llm.TOKEN_USAGE["total"] == 0


def test_retry_exhaustion_is_bounded(runtime, monkeypatch):
    s, _ = runtime
    s.llm_provider = "openai"
    s.openai_api_key = "test"
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429)
    _transport(monkeypatch, handler)
    monkeypatch.setattr(llm.time, "sleep", lambda delay: None)
    with pytest.raises(httpx.HTTPStatusError):
        llm.chat([])
    assert len(calls) == s.llm_max_retries + 1


def test_retry_after_http_date():
    response = httpx.Response(429, request=httpx.Request("POST", "https://example.test"),
                              headers={"Retry-After": format_datetime(dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=20))})
    error = httpx.HTTPStatusError("limited", request=response.request, response=response)
    assert 18 <= llm._retry_after(error) <= 20


def test_schema_coercion_failure_returns_none(runtime):
    def invalid(raw):
        raise ValueError("not a compatible shape")
    assert llm.chat_schema([], invalid, task_kind="json", mock_context={"result": {}}) is None


def test_plain_http_chat_omits_json_options_and_accepts_pydantic_schema(runtime, monkeypatch):
    from pydantic import BaseModel
    class Result(BaseModel):
        value: int
    s, _ = runtime
    s.llm_provider = "openai"
    s.openai_api_key = "test"
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return _response('{"value":4}')
    _transport(monkeypatch, handler)
    assert llm.chat([]) == '{"value":4}'
    assert "response_format" not in requests[0]
    assert llm.chat_schema([], Result.model_validate, schema=Result).value == 4
    assert '"value"' in requests[1]["messages"][0]["content"]


def test_exhausted_daily_bucket_does_not_block_other_tier():
    limiter = ratelimit.RateLimiter()
    for tier in ("core", "fast"):
        limiter.configure(tier, rpm=0, rpd=1, tpm=0, max_concurrency=1)
    with ratelimit.slot(limiter, "core"):
        pass
    with pytest.raises(ratelimit.DailyQuotaExhausted):
        limiter.acquire("core")
    assert limiter._waiting == []
    with ratelimit.slot(limiter, "fast"):
        pass
    assert limiter.snapshot()["fast"]["rpd_used"] == 1
