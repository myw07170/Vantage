"""Summarize a saved report and the source context actually supplied per stage.

Usage: python scripts/summarize_report.py report.json [--out summary.json]
No credentials, database connection, model call or network access is needed.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def summarize(report: dict) -> dict:
    sources = {e["evidence_id"]: e for e in report.get("evidence", [])}
    stages = defaultdict(lambda: {"model_calls": 0, "tokens": 0, "context_by_product": Counter(),
                                  "unknown_context_ids": []})
    for span in report.get("trace", []):
        if not (span.get("total_tokens") or span.get("model", "").startswith("mock:")):
            continue
        stage = stages[span["stage"]]
        stage["model_calls"] += 1
        stage["tokens"] += span.get("total_tokens", 0)
        for eid in span.get("evidence_ids", []):
            if eid in sources:
                stage["context_by_product"][sources[eid].get("brand", "")] += 1
            else:
                stage["unknown_context_ids"].append(eid)
    review = report.get("verify_review", {})
    return {
        "report_id": report.get("id"), "provider": report.get("llm_provider"),
        "is_mock": report.get("is_mock"), "products": report.get("brands", []),
        "usage": report.get("metrics", {}).get("efficiency", {}),
        "collected_by_product": dict(Counter(e.get("brand", "") for e in sources.values())),
        "source_types": dict(Counter(e.get("source_type", "") for e in sources.values())),
        "publication_date_unknown": sum(not e.get("published_at") for e in sources.values()),
        "bounded_source_contexts_saved": sum(bool(e.get("full_text")) for e in sources.values()),
        "stages": dict(stages),
        "dimension_coverage": report.get("quality_after", {}).get("coverage_by_dimension", {}),
        "verification": {key: review.get(key) for key in (
            "verdict", "review_complete", "recheck_status", "rewritten_sections",
            "resolved_findings", "findings", "checks")},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = summarize(json.loads(args.report.read_text(encoding="utf-8")))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
