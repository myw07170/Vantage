"""Public-web collection must not connect to internal targets or unbounded bodies."""
import ipaddress
import gzip
import socket

import httpx
import pytest

from app.core import fetcher, orchestrator as pipeline


@pytest.fixture
def public_dns(monkeypatch):
    def resolve(host, port, **kwargs):
        try:
            address = str(ipaddress.ip_address(host))
        except ValueError:
            address = "127.0.0.1" if host.endswith(".internal") else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]
    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(fetcher, "_POLITENESS_DELAY", 0)
    fetcher._cache.clear()


@pytest.mark.parametrize("url", ["http://127.0.0.1/admin", "http://10.1.2.3", "http://192.168.1.1",
                                 "http://169.254.169.254/latest/meta-data", "http://[::1]", "http://[fc00::1]",
                                 "http://[::ffff:127.0.0.1]", "http://224.0.0.1", "http://app.internal",
                                 "file:///etc/passwd", "javascript:alert(1)", "https://user:pass@public.test"])
def test_unsafe_urls_rejected_even_with_prefetched_content(public_dns, monkeypatch, url):
    def forbidden(*args, **kwargs):
        pytest.fail("Blocked URL reached HTTP client")
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    result = fetcher.fetch_page(url, prefetched_text="secret " * 100, fallback_snippet="unsafe fallback")
    assert result["blocked"] and not result["ok"] and not result["text"]


def _mock_http(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler)))


def test_redirect_to_internal_is_blocked_and_not_requested(public_dns, monkeypatch):
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
    _mock_http(monkeypatch, handler)
    result = fetcher.fetch_page("https://public.test/article", fallback_snippet="safe source excerpt")
    assert result["blocked"] and not result["text"]
    assert seen == ["https://public.test/article"]


def test_public_redirect_and_body_extraction(public_dns, monkeypatch):
    def handler(request):
        if request.url.path == "/before":
            return httpx.Response(302, headers={"location": "/article"})
        return httpx.Response(200, text='<html><p>Public source evidence about product pricing and features.</p>'
                             '<img src="/image.jpg"></html>')
    _mock_http(monkeypatch, handler)
    result = fetcher.fetch_page("https://public.test/before")
    assert result["ok"] and "Public source evidence" in result["text"]
    assert result["images"][0]["src"] == "https://public.test/image.jpg"


@pytest.mark.parametrize("declared", [False, True])
def test_body_limit_applies_with_or_without_content_length(public_dns, monkeypatch, declared):
    class Chunks(httpx.SyncByteStream):
        def __iter__(self):
            yield b"x" * 20
            yield b"x" * 20
    monkeypatch.setattr(fetcher, "_MAX_BODY", 30)
    _mock_http(monkeypatch, lambda request: httpx.Response(
        200, stream=Chunks(), headers={"content-length": "40"} if declared else {}))
    result = fetcher.fetch_page("https://public.test/large", fallback_snippet="bounded public snippet")
    assert not result["ok"] and result["degraded"] and result["text"] == "bounded public snippet"


def test_connection_pins_public_ip_with_original_host_and_tls_sni(public_dns, monkeypatch):
    received = []
    def send(self, request):
        received.append(request)
        return httpx.Response(200)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", send)
    with fetcher.PublicHTTPTransport() as transport:
        transport.handle_request(httpx.Request("GET", "https://public.test:8443/article"))
    request = received[0]
    assert request.url.host == "93.184.216.34" and request.url.port == 8443
    assert request.headers["host"] == "public.test:8443"
    assert request.extensions["sni_hostname"] == "public.test"


def test_compressed_body_is_decoded_once(public_dns, monkeypatch):
    body = gzip.compress(b'<html><p>Compressed public source evidence about product pricing.</p></html>')
    _mock_http(monkeypatch, lambda request: httpx.Response(
        200, content=body, headers={"content-encoding": "gzip"}))
    result = fetcher.fetch_page("https://public.test/compressed")
    assert result["ok"] and "Compressed public source evidence" in result["text"]


def test_mixed_public_private_dns_answers_are_rejected(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))])
    with pytest.raises(fetcher.UnsafeURL):
        fetcher.public_addresses("https://public.test")


def test_rebinding_cannot_change_validated_connection_to_private(public_dns, monkeypatch):
    seen = []
    answers = iter(["93.184.216.34", "127.0.0.1"])
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (next(answers), 443))])
    assert fetcher.public_addresses("https://public.test") == ["93.184.216.34"]
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda *args: seen.append(args))
    with fetcher.PublicHTTPTransport() as transport:
        with pytest.raises(fetcher.UnsafeURL):
            transport.handle_request(httpx.Request("GET", "https://public.test"))
    assert not seen


def test_blocked_source_never_becomes_evidence(offline, monkeypatch):
    monkeypatch.setattr(pipeline, "fetch_page", lambda *args, **kw: {"blocked": True, "text": "", "ok": False})
    result = pipeline._collect_brand("Notion", ["pricing"], "collector", 6, "year", set(), "t_test")
    assert not result["evidences"]
