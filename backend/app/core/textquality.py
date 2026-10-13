"""Text-quality filters for fetched pages.

Two failure modes this guards against:
  * `is_garbled` — mis-decoded bytes, binary blobs, or pages that are mostly
    markup residue rather than prose.
  * `is_relevant_content` — the search result looked on-topic from its title
    and snippet, but the actual article is about something else.
"""
from __future__ import annotations

import re
import unicodedata

_REPLACEMENT = "�"  # the U+FFFD replacement character


def _is_readable(ch: str) -> bool:
    """True for characters that legitimately appear in prose.

    Uses Unicode general categories rather than an explicit character class, so
    accented Latin (é, ñ, ü), curly quotes, dashes and symbols all count as
    readable. A hardcoded ASCII class would flag ordinary English text
    containing "café" or "naïve" as garbled.
    """
    if ch.isspace():
        return True
    cat = unicodedata.category(ch)
    # L* letters, N* numbers, P* punctuation, Sm/Sc math and currency symbols.
    return cat[0] in ("L", "N", "P") or cat in ("Sm", "Sc")


def is_garbled(text: str) -> bool:
    """Heuristic: does this look like mis-decoded or non-prose content?"""
    if not text:
        return False
    n = len(text)
    if n < 10:
        return False

    # Too many replacement characters — a decode already failed upstream.
    if text.count(_REPLACEMENT) / n > 0.02:
        return True

    # Control characters that are not whitespace.
    ctrl = sum(1 for c in text if ord(c) < 32 and c not in "\n\r\t")
    if ctrl / n > 0.05:
        return True

    # Mostly unreadable code points.
    readable = sum(1 for c in text if _is_readable(c))
    if readable / n < 0.6:
        return True

    return False


def _keywords(query: str, brands) -> set[str]:
    kws = set()
    for b in brands or []:
        if b:
            kws.add(str(b).lower())
    for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", (query or "").lower()):
        kws.add(w)
    return {k for k in kws if k}


def is_relevant_content(text: str, brands, query: str = "") -> bool:
    """Second-pass relevance check on the extracted body.

    Deliberately permissive — one brand or keyword hit is enough. Over-filtering
    here costs evidence, whereas a weakly-relevant page is already penalized by
    its credibility score. Short texts (usually a snippet fallback) always pass.
    """
    if not text or len(text) < 80:
        return True
    low = text.lower()
    for b in brands or []:
        if b and str(b).lower() in low:
            return True
    kws = _keywords(query, brands)
    if not kws:
        return True
    return any(k in low for k in kws)
