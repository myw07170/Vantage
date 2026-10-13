"""Real page fetching: HTML → article body + images.

httpx pulls the page, trafilatura extracts the body, BeautifulSoup picks up
images and the OG preview. Never raises: on any failure it degrades to the
search snippet and flags `degraded`, so one dead link cannot abort a run.

Two additions over a naive fetcher, both of which matter because the collect
stage re-runs during rework rounds:
  * a per-domain politeness delay, so a rework burst does not hammer one host;
  * a small in-process cache, so the same URL is not fetched twice in a run.
"""
from __future__ import annotations

import datetime as _dt
import ipaddress
import socket
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse

import httpx

from app.core.textquality import is_garbled

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_TIMEOUT = httpx.Timeout(connect=8, read=20, write=5, pool=5)
_MAX_BODY = 2 * 1024 * 1024
_MAX_REDIRECTS = 5


class UnsafeURL(ValueError):
    """A source must never reach a local or private network service."""


def public_addresses(url: str) -> list[str]:
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL as exc:
        raise UnsafeURL("Invalid source URL.") from exc
    if parsed.scheme not in ("http", "https") or not parsed.host or parsed.userinfo:
        raise UnsafeURL("Only public HTTP/HTTPS source URLs are allowed.")
    try:
        addresses = list(dict.fromkeys(
            row[4][0] for row in socket.getaddrinfo(parsed.host, parsed.port or (443 if parsed.scheme == "https" else 80),
                                                  type=socket.SOCK_STREAM)
        ))
    except OSError as exc:
        raise UnsafeURL("Source hostname could not be resolved safely.") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global or
                            ipaddress.ip_address(address).is_multicast for address in addresses):
        raise UnsafeURL("Local, private and reserved source addresses are blocked.")
    return addresses


class PublicHTTPTransport(httpx.HTTPTransport):
    """Connect to the validated address, keeping the original Host and TLS SNI."""
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        addresses = public_addresses(str(request.url))
        pinned = httpx.Request(
            request.method, request.url.copy_with(host=addresses[0]),
            headers=request.headers, stream=request.stream,
            extensions={**request.extensions, "sni_hostname": request.url.host},
        )
        return super().handle_request(pinned)

# Minimum gap between requests to the same host.
_POLITENESS_DELAY = 1.0
_domain_last: Dict[str, float] = {}
_domain_lock = threading.Lock()

# Small LRU so rework rounds reuse pages instead of re-downloading them.
_CACHE_MAX = 256
_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_cache_lock = threading.Lock()


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _wait_turn(domain: str) -> None:
    if not domain:
        return
    with _domain_lock:
        last = _domain_last.get(domain, 0.0)
        gap = time.monotonic() - last
        wait = _POLITENESS_DELAY - gap
        # Reserve the slot before sleeping so concurrent callers queue rather
        # than all computing the same (short) wait and firing together.
        _domain_last[domain] = time.monotonic() + max(0.0, wait)
    if wait > 0:
        time.sleep(wait)


def _cache_get(url: str) -> Dict[str, Any] | None:
    with _cache_lock:
        hit = _cache.get(url)
        if hit is not None:
            _cache.move_to_end(url)
            return dict(hit)
    return None


def _cache_put(url: str, value: Dict[str, Any]) -> None:
    with _cache_lock:
        _cache[url] = dict(value)
        _cache.move_to_end(url)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)


def fetch_page(
    url: str, *, fallback_snippet: str = "", prefetched_text: str = ""
) -> Dict[str, Any]:
    """Fetch one page's body text and images.

    Args:
        fallback_snippet: used as the text if the fetch or extraction fails.
        prefetched_text: body text a search provider already returned (Exa and
            Tavily do). When present the network round-trip is skipped entirely
            — but images and the OG cover are then unavailable.

    Returns `{url, text, images, og_image, ok, degraded, captured_at}`.
    """
    try:
        public_addresses(url)
    except (UnsafeURL, httpx.InvalidURL, ValueError) as exc:
        return {"url": url, "text": "", "images": [], "og_image": "", "ok": False,
                "degraded": True, "blocked": True, "reason": str(exc), "captured_at": _now()}
    if prefetched_text and len(prefetched_text) >= 200:
        return {
            "url": url,
            "text": prefetched_text[:4000],
            "images": [],
            "og_image": "",
            "ok": True,
            "degraded": False,
            "captured_at": _now(),
        }

    cached = _cache_get(url)
    if cached is not None:
        return cached

    result: Dict[str, Any] = {
        "url": url,
        "text": fallback_snippet,
        "images": [],
        "og_image": "",
        "ok": False,
        "degraded": True,
    }
    try:
        _wait_turn(domain_of(url))
        with httpx.Client(
            timeout=_TIMEOUT,
            follow_redirects=False,
            transport=PublicHTTPTransport(),
            trust_env=False,
            headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"},
        ) as client:
            current_url = url
            for hop in range(_MAX_REDIRECTS + 1):
                public_addresses(current_url)
                with client.stream("GET", current_url) as r:
                    if r.status_code in (301, 302, 303, 307, 308):
                        if hop == _MAX_REDIRECTS or not r.headers.get("location"):
                            raise ValueError("Too many or invalid source redirects.")
                        current_url = urljoin(current_url, r.headers["location"])
                        continue
                    r.raise_for_status()
                    if int(r.headers.get("content-length", "0")) > _MAX_BODY:
                        raise ValueError("Source response exceeds the body limit.")
                    body = bytearray()
                    for chunk in r.iter_bytes(chunk_size=65536):
                        body.extend(chunk)
                        if len(body) > _MAX_BODY:
                            raise ValueError("Source response exceeds the body limit.")
                    headers = {k: v for k, v in r.headers.items() if k not in ("content-encoding", "content-length")}
                    r = httpx.Response(r.status_code, headers=headers, content=bytes(body), request=r.request)
                    break
            html = r.text
            # httpx decodes using the declared charset; a wrong declaration
            # yields mojibake. Retry the common Western encodings on the raw
            # bytes before giving up.
            if is_garbled(html[:2000]):
                declared = (r.encoding or "").lower()
                for cand in ("utf-8", "cp1252", "latin-1"):
                    if cand == declared:
                        continue
                    try:
                        redecoded = r.content.decode(cand, errors="strict")
                    except Exception:
                        continue
                    if not is_garbled(redecoded[:2000]):
                        html = redecoded
                        break

        text = _extract_text(html) or fallback_snippet
        if text and is_garbled(text):
            text = fallback_snippet
        result.update(
            {
                "text": text[:4000],
                "images": _extract_images(html, current_url)[:6],
                "og_image": _extract_og_image(html, current_url),
                "ok": True,
                "degraded": False,
            }
        )
    except UnsafeURL as exc:
        result.update(text="", blocked=True, reason=str(exc))
    except Exception:
        # Degrade to the snippet — credibility scoring already penalizes this.
        pass

    result["captured_at"] = _now()
    if result["ok"]:
        _cache_put(url, result)
    return result


def _extract_text(html: str) -> str:
    try:
        import trafilatura

        out = trafilatura.extract(html, include_comments=False, include_tables=False)
        if out:
            return out.strip()
    except Exception:
        pass
    # Fallback: pull the paragraph tags directly.
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        ps = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        return "\n".join(p for p in ps if len(p) > 20)
    except Exception:
        return ""


def _extract_images(html: str, base_url: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if not src or src.startswith("data:"):
                continue
            if _looks_like_icon(src):
                continue
            out.append(
                {
                    "src": urljoin(base_url, src),
                    "alt": (img.get("alt") or "").strip(),
                    "source_url": base_url,
                }
            )
            if len(out) >= 8:
                break
    except Exception:
        pass
    return out


def _extract_og_image(html: str, base_url: str) -> str:
    """The OG/Twitter share image — the most representative, traceable visual."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for attr, value in (
            ("property", "og:image"),
            ("property", "og:image:url"),
            ("name", "twitter:image"),
            ("name", "twitter:image:src"),
            ("itemprop", "image"),
        ):
            tag = soup.find("meta", attrs={attr: value})
            if tag and tag.get("content"):
                src = tag["content"].strip()
                if src and not src.startswith("data:"):
                    return urljoin(base_url, src)
        link = soup.find("link", attrs={"rel": "image_src"})
        if link and link.get("href"):
            return urljoin(base_url, link["href"].strip())
    except Exception:
        pass
    return ""


_ICON_HINTS = (
    "logo", "icon", "sprite", "avatar", "favicon", "blank", "spacer",
    "pixel", "1x1", "tracking", "beacon",
)


def _looks_like_icon(src: str) -> bool:
    s = src.lower()
    return any(h in s for h in _ICON_HINTS)
