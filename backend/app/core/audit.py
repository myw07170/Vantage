"""Quality gate and rework loop.

`evaluate_quality` scores the analysis against rules; `llm_quality_review` adds
a model's editorial read; `decide_rework` turns findings into `REWORK`
envelopes addressed at the stage that can fix them.

This implements the third iron rule: when quality falls short the pipeline goes
back and collects more, rather than lowering the bar and shipping.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.fetcher import domain_of
from app.core.models import Envelope

# Score dimension keys. The frontend's audit panel renders these directly, so
# they are part of the API contract — changing one is a cross-stack change.
DIM_EVIDENCE = "Evidence sufficiency"
DIM_COVERAGE = "Dimension coverage"
DIM_CONFIDENCE = "Conclusion confidence"
DIM_STRUCTURE = "Structured completeness"
DIM_CROSS_VALIDATION = "Cross-validation"


@dataclass
class QualityReport:
    coverage_by_dimension: Dict[str, bool] = field(default_factory=dict)
    coverage_by_brand: Dict[str, Dict[str, int]] = field(default_factory=dict)
    confidence_ratio: float = 0.0
    schema_completeness: float = 0.0
    dimension_coverage_rate: float = 0.0
    brand_coverage_rate: float = 0.0
    issues: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "coverage_by_dimension": self.coverage_by_dimension,
            "coverage_by_brand": self.coverage_by_brand,
            "confidence_ratio": self.confidence_ratio,
            "schema_completeness": self.schema_completeness,
            "dimension_coverage_rate": self.dimension_coverage_rate,
            "brand_coverage_rate": self.brand_coverage_rate,
            "issues": self.issues,
        }

    def summary(self) -> Dict[str, Any]:
        """Condensed metrics for the frontend's rework card."""
        return {
            "confidence_ratio": round(self.confidence_ratio * 100),
            "dimension_coverage": round(self.dimension_coverage_rate * 100),
            "brand_coverage": round(self.brand_coverage_rate * 100),
            "schema_completeness": round(self.schema_completeness * 100),
        }


# Maps a structured field to the research-focus wording that implies it, so the
# audit can tell whether a requested dimension actually got covered.
_FIELD_KEYWORDS = {
    "pricing_model": ("pricing", "price", "cost", "plan", "tier", "subscription", "billing"),
    "feature_tree": ("feature", "capability", "functionality", "product", "roadmap"),
    "user_persona": ("user", "persona", "customer", "segment", "audience", "buyer", "icp"),
    "trend": ("trend", "growth", "trajectory", "outlook", "forecast", "momentum"),
    "swot": ("swot", "strength", "weakness", "opportunity", "threat", "positioning"),
}


def evaluate_quality(
    brands: List[str],
    focus: List[str],
    claims: List[Dict[str, Any]],
    evidences: List[Any],
    structured: Dict[str, Any],
    *,
    min_indep_domains: int = 2,
) -> QualityReport:
    qr = QualityReport()

    # 1. Share of claims that reached high confidence.
    total = len(claims) or 1
    high = sum(1 for c in claims if c.get("confidence") == "high")
    qr.confidence_ratio = round(high / total, 3)

    # 2. Dimension coverage: does each requested focus have a solid claim?
    fields_present = {
        c.get("field") for c in claims if c.get("confidence") in ("high", "medium")
    }
    for dim in focus:
        covered = False
        low = dim.lower()
        for f, kws in _FIELD_KEYWORDS.items():
            if f in fields_present and any(k in low for k in kws):
                covered = True
                break
        # Fall back to "any valid claim touches this" rather than reporting a
        # false gap when the focus wording does not match a known field.
        if not covered and fields_present:
            covered = True
        qr.coverage_by_dimension[dim] = covered
    covered_dims = sum(1 for v in qr.coverage_by_dimension.values() if v)
    qr.dimension_coverage_rate = round(covered_dims / (len(focus) or 1), 3)

    # 3. Per-brand evidence and independent-domain counts.
    brand_ok = 0
    for b in brands:
        evs = [e for e in evidences if getattr(e, "brand", "") == b]
        domains = {domain_of(getattr(e, "source_url", "")) for e in evs}
        domains.discard("")
        qr.coverage_by_brand[b] = {"evidence": len(evs), "domains": len(domains)}
        if len(domains) >= min_indep_domains:
            brand_ok += 1
        else:
            qr.issues.append(
                {
                    "issue_id": "is_" + uuid.uuid4().hex[:8],
                    "target": f"brand:{b}",
                    "severity": "high" if len(evs) == 0 else "medium",
                    "reason": (
                        f"\"{b}\" has only {len(domains)} independent source(s) "
                        f"(fewer than {min_indep_domains}). Evidence is too thin "
                        "to cross-validate — collect more."
                    ),
                    "raised_by": "L3-003",
                }
            )
    qr.brand_coverage_rate = round(brand_ok / (len(brands) or 1), 3)

    # 4. Uncovered dimensions.
    for dim, ok in qr.coverage_by_dimension.items():
        if not ok:
            qr.issues.append(
                {
                    "issue_id": "is_" + uuid.uuid4().hex[:8],
                    "target": f"dimension:{dim}",
                    "severity": "medium",
                    "reason": (
                        f"Dimension \"{dim}\" has no supporting claims. Re-run "
                        "the analysis against this angle."
                    ),
                    "raised_by": "L3-003",
                }
            )

    # 5. Structured-schema completeness.
    from app.core.schemas import schema_completeness

    qr.schema_completeness = schema_completeness(structured)
    if qr.schema_completeness < 0.34:
        qr.issues.append(
            {
                "issue_id": "is_" + uuid.uuid4().hex[:8],
                "target": "schema",
                "severity": "low",
                "reason": (
                    "Structured knowledge (feature tree / pricing / personas) is "
                    "mostly empty. Re-analyze to fill it in."
                ),
                "raised_by": "L3-003",
            }
        )

    return qr


def llm_quality_review(
    query: str,
    brands: List[str],
    focus: List[str],
    claims: List[Dict[str, Any]],
    structured: Dict[str, Any],
    qr: "QualityReport",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """The quality officer's editorial read — judgement the rules cannot encode.

    Rules catch thin sourcing and missing dimensions. They cannot tell whether a
    conclusion actually follows from its evidence, so this asks a model to
    review like a managing editor and return per-dimension scores, concrete
    problems and actionable fixes. Falls back to the rule metrics if it fails.
    """
    from app.core.llm import chat_json

    claim_lines = (
        "\n".join(
            f"- [{c.get('confidence','?')}|{c.get('field','')}] {c.get('text','')}"
            for c in claims[:18]
        )
        or "(no claims yet)"
    )
    sc_dims = (
        ", ".join(
            f"{k}: {'covered' if v else 'MISSING'}"
            for k, v in qr.coverage_by_dimension.items()
        )
        or "none"
    )
    brand_cov = (
        ", ".join(
            f"{b} ({v.get('domains',0)} domains / {v.get('evidence',0)} evidence)"
            for b, v in qr.coverage_by_brand.items()
        )
        or "none"
    )
    fallback = {
        "verdict": "pass" if not qr.issues else "rework",
        "scores": {
            DIM_EVIDENCE: round(qr.brand_coverage_rate * 100),
            DIM_COVERAGE: round(qr.dimension_coverage_rate * 100),
            DIM_CONFIDENCE: round(qr.confidence_ratio * 100),
            DIM_STRUCTURE: round(qr.schema_completeness * 100),
        },
        "review": (
            f"Rule-based assessment: {round(qr.dimension_coverage_rate*100)}% dimension "
            f"coverage, {round(qr.brand_coverage_rate*100)}% brand coverage, "
            f"{round(qr.confidence_ratio*100)}% of claims at high confidence."
        ),
        "issues": [i.get("reason", "") for i in qr.issues[:6]],
        "suggestions": [],
    }
    try:
        data = chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You are the quality officer on a competitive-intelligence "
                        "research team (L3, decision tier). Review the analysis "
                        "work-in-progress below the way a managing editor or an "
                        "equity-research supervisory analyst would before sign-off.\n\n"
                        "Score each dimension 0-100 as an integer. Use the full range "
                        "and give genuinely different scores — do not return round "
                        "multiples of ten across the board. Name specific problems "
                        "(vague attribution, single-sourced claims, unsupported "
                        "quantities, missing angles) and give fixes someone could act "
                        "on. Then rule overall: 'pass' if this is ready to write up, "
                        "'rework' if it needs more collection or re-analysis.\n\n"
                        'Return JSON only: {"verdict":"pass|rework","scores":'
                        f'{{"{DIM_EVIDENCE}":int,"{DIM_COVERAGE}":int,'
                        f'"{DIM_CONFIDENCE}":int,"{DIM_STRUCTURE}":int,'
                        f'"{DIM_CROSS_VALIDATION}":int}},'
                        '"review":"one paragraph naming both strengths and gaps",'
                        '"issues":["specific problem 1","specific problem 2"],'
                        '"suggestions":["actionable fix 1","actionable fix 2"]}'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Research topic: {query}\n"
                        f"Competitors: {', '.join(brands)}\n"
                        f"Focus areas: {', '.join(focus)}\n\n"
                        f"Rule-side metrics -> dimension coverage: {sc_dims}; "
                        f"brand evidence coverage: {brand_cov}; "
                        f"high-confidence share: {round(qr.confidence_ratio*100)}%; "
                        f"structured completeness: {round(qr.schema_completeness*100)}%\n\n"
                        f"Claims extracted so far:\n{claim_lines}"
                    ),
                },
            ],
            max_tokens=2000,
            temperature=0.3,
            model=model,
            purpose="Quality review: score dimensions, list issues and fixes",
        )
        if isinstance(data, dict) and data.get("scores"):
            scores = {
                str(k): _clamp_score(v) for k, v in (data.get("scores") or {}).items()
            }
            return {
                "verdict": "rework" if str(data.get("verdict")) == "rework" else "pass",
                "scores": scores or fallback["scores"],
                "review": str(data.get("review") or fallback["review"]),
                "issues": [
                    str(x) for x in (data.get("issues") or []) if str(x).strip()
                ][:8],
                "suggestions": [
                    str(x) for x in (data.get("suggestions") or []) if str(x).strip()
                ][:8],
            }
    except Exception:
        pass
    return fallback


def _clamp_score(v) -> int:
    try:
        return max(0, min(100, int(round(float(v)))))
    except (TypeError, ValueError):
        return 0


def decide_rework(qr: QualityReport) -> List[Envelope]:
    """Turn quality findings into rework messages addressed at a pipeline stage.

    Thin evidence goes back to `collect`; missing dimensions or empty schemas go
    back to `analyze`. Routing by cause is what makes the loop converge instead
    of re-running everything.
    """
    envelopes: List[Envelope] = []

    collect_targets = [i for i in qr.issues if i["target"].startswith("brand:")]
    if collect_targets:
        brands_to_recollect = [i["target"].split(":", 1)[1] for i in collect_targets]
        envelopes.append(
            Envelope(
                msg_id="env_" + uuid.uuid4().hex[:8],
                sender="L3-003",
                receiver="collect",
                task_type="REWORK",
                payload={
                    "brands": brands_to_recollect,
                    "reason": "Insufficient evidence — collect more sources",
                },
                issues=collect_targets,
            )
        )

    analyze_targets = [
        i
        for i in qr.issues
        if i["target"].startswith("dimension:") or i["target"] == "schema"
    ]
    if analyze_targets:
        envelopes.append(
            Envelope(
                msg_id="env_" + uuid.uuid4().hex[:8],
                sender="L3-003",
                receiver="analyze",
                task_type="REWORK",
                payload={
                    "reason": "Dimension or structural coverage is incomplete — re-analyze"
                },
                issues=analyze_targets,
            )
        )

    return envelopes
