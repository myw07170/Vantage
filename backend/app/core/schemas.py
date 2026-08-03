"""Structured competitive-knowledge schemas: feature tree, pricing, personas.

Each type ships a tolerant `coerce_*(raw, valid_evidence_ids)` function that
drops malformed fields instead of raising, so a partially-good model response
still yields usable structure.

The important part is `_filter_eids`: any `evidence_ids` the model invents that
are not in the real evidence set are silently discarded. That is the mechanism
that stops a fabricated citation from ever reaching the report — a claim whose
citations all get filtered out drops to `unverified` rather than looking sourced.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _as_list(v) -> list:
    if isinstance(v, list):
        return v
    if v in (None, ""):
        return []
    return [v]


def _str(v, default: str = "") -> str:
    return str(v).strip() if isinstance(v, (str, int, float)) else default


def _filter_eids(raw, valid: set) -> List[str]:
    """Keep only evidence IDs that actually exist. Hallucination suppression."""
    return [e for e in _as_list(raw) if isinstance(e, str) and e in valid]


# ── feature tree ──────────────────────────────────────────────────────────────
def coerce_feature_tree(
    raw: Any, valid_eids: Optional[set] = None
) -> List[Dict[str, Any]]:
    """-> [{brand, modules:[{category,name,sub_features:[{name,support,note,evidence_ids}]}]}]"""
    valid = valid_eids or set()
    out: List[Dict[str, Any]] = []
    items = (
        raw
        if isinstance(raw, list)
        else (raw.get("feature_tree") if isinstance(raw, dict) else None)
    )
    for it in _as_list(items):
        if not isinstance(it, dict):
            continue
        brand = _str(it.get("brand"))
        if not brand:
            continue
        modules = []
        for m in _as_list(it.get("modules")):
            if not isinstance(m, dict):
                continue
            subs = []
            for sf in _as_list(m.get("sub_features")):
                if not isinstance(sf, dict):
                    continue
                support = _str(sf.get("support"), "partial").lower()
                if support not in ("full", "partial", "none"):
                    support = "partial"
                subs.append(
                    {
                        "name": _str(sf.get("name")),
                        "support": support,
                        "note": _str(sf.get("note")),
                        "evidence_ids": _filter_eids(sf.get("evidence_ids"), valid),
                    }
                )
            modules.append(
                {
                    "category": _str(m.get("category")),
                    "name": _str(m.get("name")),
                    "sub_features": [s for s in subs if s["name"]],
                }
            )
        out.append(
            {
                "brand": brand,
                "modules": [m for m in modules if m["name"] or m["sub_features"]],
            }
        )
    return out


# ── pricing model ─────────────────────────────────────────────────────────────
def coerce_pricing_model(
    raw: Any, valid_eids: Optional[set] = None
) -> List[Dict[str, Any]]:
    """-> [{brand,currency,model_type,free_tier,tiers:[{name,price,period,...}]}]"""
    valid = valid_eids or set()
    out: List[Dict[str, Any]] = []
    items = (
        raw
        if isinstance(raw, list)
        else (raw.get("pricing_model") if isinstance(raw, dict) else None)
    )
    valid_types = ("subscription", "usage", "freemium", "one_time", "free", "custom")
    for it in _as_list(items):
        if not isinstance(it, dict):
            continue
        brand = _str(it.get("brand"))
        if not brand:
            continue
        mt = _str(it.get("model_type"), "subscription").lower()
        if mt not in valid_types:
            mt = "subscription"
        tiers = []
        for t in _as_list(it.get("tiers")):
            if not isinstance(t, dict):
                continue
            price = t.get("price")
            if isinstance(price, str):
                cleaned = (
                    price.replace("$", "")
                    .replace("USD", "")
                    .replace(",", "")
                    .replace("/mo", "")
                    .replace("/month", "")
                    .strip()
                )
                try:
                    price = float(cleaned)
                except Exception:
                    price = None
            if not isinstance(price, (int, float)):
                price = None
            tiers.append(
                {
                    "name": _str(t.get("name")),
                    "price": price,
                    "period": _str(t.get("period"), "month"),
                    "unit": _str(t.get("unit"), "per user"),
                    "target_user": _str(t.get("target_user")),
                    "includes": [
                        _str(x) for x in _as_list(t.get("includes")) if _str(x)
                    ],
                    "evidence_ids": _filter_eids(t.get("evidence_ids"), valid),
                }
            )
        out.append(
            {
                "brand": brand,
                "currency": _str(it.get("currency"), "USD"),
                "model_type": mt,
                "free_tier": bool(it.get("free_tier")),
                "tiers": [t for t in tiers if t["name"]],
            }
        )
    return out


# ── user personas ─────────────────────────────────────────────────────────────
def coerce_user_persona(
    raw: Any, valid_eids: Optional[set] = None
) -> List[Dict[str, Any]]:
    """-> [{brand,personas:[{name,segment,needs,scenarios,pain_points,...}]}]"""
    valid = valid_eids or set()
    out: List[Dict[str, Any]] = []
    items = (
        raw
        if isinstance(raw, list)
        else (raw.get("user_persona") if isinstance(raw, dict) else None)
    )
    for it in _as_list(items):
        if not isinstance(it, dict):
            continue
        brand = _str(it.get("brand"))
        if not brand:
            continue
        personas = []
        for p in _as_list(it.get("personas")):
            if not isinstance(p, dict):
                continue
            personas.append(
                {
                    "name": _str(p.get("name")),
                    "segment": _str(p.get("segment")),
                    "needs": [_str(x) for x in _as_list(p.get("needs")) if _str(x)],
                    "scenarios": [
                        _str(x) for x in _as_list(p.get("scenarios")) if _str(x)
                    ],
                    "pain_points": [
                        _str(x) for x in _as_list(p.get("pain_points")) if _str(x)
                    ],
                    "decision_factors": [
                        _str(x) for x in _as_list(p.get("decision_factors")) if _str(x)
                    ],
                    "migration_cost": _str(p.get("migration_cost")),
                    "evidence_ids": _filter_eids(p.get("evidence_ids"), valid),
                }
            )
        out.append({"brand": brand, "personas": [p for p in personas if p["name"]]})
    return out


def schema_completeness(structured: Dict[str, Any]) -> float:
    """Fraction of the three schema types that got populated (0-1).

    Feeds the audit stage and the consistency metric.
    """
    ft = structured.get("feature_tree") or []
    pm = structured.get("pricing_model") or []
    up = structured.get("user_persona") or []
    filled = 0
    expected = 3
    if any(b.get("modules") for b in ft):
        filled += 1
    if any(b.get("tiers") for b in pm):
        filled += 1
    if any(b.get("personas") for b in up):
        filled += 1
    return round(filled / expected, 3) if expected else 0.0
