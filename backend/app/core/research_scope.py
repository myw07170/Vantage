"""Explicit product scope and conservative vendor provenance."""
from __future__ import annotations

import re
from urllib.parse import urlparse

# These domains establish vendor provenance, not the truth of vendor claims.
VENDOR_DOMAINS = {
    "notion": ("notion.so", "notion.com"),
    "obsidian": ("obsidian.md",),
    "claude code": ("anthropic.com", "claude.com", "claude.ai"),
    "codex": ("openai.com",),
    "github copilot": ("github.com", "github.blog", "microsoft.com"),
    "cursor": ("cursor.com", "cursor.sh", "anysphere.inc"),
    "slack": ("slack.com",),
    "microsoft teams": ("microsoft.com",),
    "linear": ("linear.app",),
    "asana": ("asana.com",),
    "clickup": ("clickup.com",),
    "craft": ("craft.do",),
}


def is_category(name: str) -> bool:
    return bool(re.search(r"\b(market|landscape|industry|comparison|analysis|category|versus|vs)\b|市场|行业|竞品分析|产品对比", name, re.I)) or name.strip().lower() in {
        "ai coding assistant", "ai coding assistants", "saas", "software", "coding assistants",
    }


def product_names(raw) -> list[str]:
    if not isinstance(raw, list) or any(not isinstance(n, str) for n in raw):
        raise ValueError("Select specific product names before confirming research.")
    names, seen = [], set()
    for entry in raw:
        name = entry.strip()
        if not name or len(name) > 100 or is_category(name):
            raise ValueError(f'"{name}" is not a specific research product. Correct the product list.')
        if name.casefold() not in seen:
            seen.add(name.casefold())
            names.append(name)
    if not 2 <= len(names) <= 6:
        raise ValueError("Confirm between 2 and 6 specific products for this research.")
    return names


def is_vendor_source(url: str, brand: str = "") -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    # Vendor-operated hosting can contain third-party content.
    if host in ("gist.github.com", "publish.obsidian.md"):
        return False
    if host in ("github.com", "www.github.com"):
        return brand.casefold() == "github copilot" and (
            parsed.path in ("", "/") or any(parsed.path.startswith(prefix) for prefix in (
                "/features/copilot", "/github/", "/pricing", "/enterprise", "/resources/", "/customer-stories/"))
        )
    if host in ("notion.so", "www.notion.so") and parsed.path not in ("", "/"):
        return brand.casefold() == "notion" and any(parsed.path.startswith(prefix) for prefix in (
            "/product", "/pricing", "/help", "/releases", "/blog", "/guides"))
    domains = VENDOR_DOMAINS.get(brand.casefold(), ()) if brand else ()
    return any(host == domain or host.endswith("." + domain) for domain in domains)
