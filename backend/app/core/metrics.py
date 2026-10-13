"""Quantified impact and business-outcome metrics.

Every number is computed from real run data and ships with the formula that
produced it, so a reader can check the arithmetic rather than trust a headline
multiplier. Baselines are constants here and disclosed in the output.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.core.fetcher import domain_of

# ── Configurable baselines, disclosed in the output as industry estimates ─────
# Average analyst minutes to read and digest one source.
MANUAL_MIN_PER_SOURCE = 8
# Independent sources a manual competitive analysis typically covers.
BASELINE_MANUAL_SOURCES = 6


def compute_report_metrics(
    *,
    brands: List[str],
    focus: List[str],
    claims: List[Dict[str, Any]],
    evidences: List[Any],
    structured: Dict[str, Any],
    elapsed_seconds: float,
    tokens_used: int,
    rework_rounds: int = 0,
    issues_resolved: int = 0,
    verify_rounds: int = 0,
    verify_issues_fixed: int = 0,
) -> Dict[str, Any]:
    indep_domains = len(
        {
            domain_of(getattr(e, "source_url", ""))
            for e in evidences
            if getattr(e, "source_url", "")
        }
        - {""}
    )
    platforms = len({getattr(e, "source_type", "") for e in evidences} - {""})
    total_claims = len(claims) or 1
    high_conf = sum(1 for c in claims if c.get("confidence") == "high")
    cross_validated = sum(1 for c in claims if c.get("cross_validated"))
    claims_with_evidence = sum(1 for c in claims if c.get("evidence_ids"))

    elapsed_min = max(0.1, elapsed_seconds / 60.0)
    manual_min = max(1, len(brands) * max(1, len(focus)) * MANUAL_MIN_PER_SOURCE)

    efficiency_multiple = round(manual_min / elapsed_min, 1)
    coverage_multiple = (
        round(indep_domains / BASELINE_MANUAL_SOURCES, 1)
        if BASELINE_MANUAL_SOURCES
        else 0
    )

    from app.core.schemas import schema_completeness

    sc = schema_completeness(structured)
    consistency = round(0.5 * (claims_with_evidence / total_claims) + 0.5 * sc, 3)

    accuracy = round(high_conf / total_claims, 3)
    cross_ratio = round(cross_validated / total_claims, 3)

    return {
        "efficiency": {
            "elapsed_seconds": round(elapsed_seconds, 1),
            "elapsed_minutes": round(elapsed_min, 1),
            "manual_estimate_minutes": manual_min,
            "efficiency_multiple": efficiency_multiple,
            "tokens_used": tokens_used,
            "formula": "manual estimate (brands x focus areas x 8 min/source) / actual elapsed time",
            "baseline_note": (
                f"Baseline: roughly {MANUAL_MIN_PER_SOURCE} analyst-minutes per source "
                "(industry estimate, configurable)"
            ),
        },
        "coverage": {
            "independent_sources": indep_domains,
            "platforms_covered": platforms,
            "evidence_total": len(evidences),
            "coverage_multiple": coverage_multiple,
            "baseline_sources": BASELINE_MANUAL_SOURCES,
            "formula": f"independent sources found / manual baseline ({BASELINE_MANUAL_SOURCES})",
        },
        "consistency": {
            "value": consistency,
            "claims_with_evidence_ratio": round(
                claims_with_evidence / total_claims, 3
            ),
            "schema_completeness": sc,
            "formula": "0.5 x (claims carrying evidence) + 0.5 x (structured schema fill rate)",
        },
        "business": {
            "accuracy": accuracy,
            "cross_validated_ratio": cross_ratio,
            "dimension_coverage": None,  # injected from the quality report
            "brand_coverage": None,      # injected from the quality report
            "correction_rate": None,     # injected from reader feedback
            "rework_rounds": rework_rounds,
            "issues_resolved": issues_resolved,
            # Post-write verification: defects found in the finished document and
            # repaired or rewritten before it shipped.
            "verify_rounds": verify_rounds,
            "verify_issues_fixed": verify_issues_fixed,
            "formula": (
                "accuracy = high-confidence claims / total claims; "
                "correction rate = edited blocks / editable blocks (updated after feedback)"
            ),
        },
    }


def merge_quality_into_metrics(
    metrics: Dict[str, Any], quality: Dict[str, Any]
) -> Dict[str, Any]:
    """Fold the audit stage's coverage rates into metrics.business."""
    if not metrics or not quality:
        return metrics
    biz = metrics.setdefault("business", {})
    biz["dimension_coverage"] = quality.get("dimension_coverage_rate")
    biz["brand_coverage"] = quality.get("brand_coverage_rate")
    return metrics


def apply_feedback(
    metrics: Dict[str, Any], edited_blocks: int, total_blocks: int
) -> Dict[str, Any]:
    """Update the human-correction rate after a reader edits the report."""
    biz = metrics.setdefault("business", {})
    if total_blocks > 0:
        biz["correction_rate"] = round(edited_blocks / total_blocks, 3)
        biz["edited_blocks"] = edited_blocks
        biz["total_blocks"] = total_blocks
    return metrics
