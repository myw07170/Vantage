"""Run the full research pipeline headlessly, with no frontend.

This is the Phase 6 gate: it validates collection, analysis, the rework loop,
writing and assembly in one shot, and asserts the invariants the product's
credibility rests on.

    uv run python scripts/run_pipeline.py --query "Notion vs Obsidian" --mode quick
    uv run python scripts/run_pipeline.py --query "..." --mode deep --verbose

Writes the assembled report JSON next to the database for inspection.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.core import db  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.orchestrator import create_task, run_pipeline, submit_clarify  # noqa: E402

# Event types that are noisy in a terminal unless --verbose.
_QUIET = {"evidence", "trace", "image", "progress"}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="Notion vs Obsidian vs Craft for research teams")
    ap.add_argument("--mode", default="quick", choices=["quick", "deep", "expert"])
    ap.add_argument("--verbose", action="store_true", help="print every event")
    ap.add_argument("--out", default="", help="where to write the report JSON")
    args = ap.parse_args()

    settings = get_settings()
    if not settings.llm_configured:
        print("FAIL  GEMINI_API_KEY is not set — copy backend/.env.example to backend/.env")
        return 1

    print(f"query: {args.query}")
    print(f"mode:  {args.mode}")
    print(f"model: {settings.gemini_model_core} / {settings.gemini_model_fast}")
    print()

    t0 = time.monotonic()
    task = create_task(args.query, mode=args.mode)
    task_id = task["taskId"]
    print(f"task {task_id} created, {len(task.get('clarifyQuestions') or [])} clarify questions")
    for q in task.get("clarifyQuestions") or []:
        print(f"  [{q['type']:6s}] {q['question']}")
        if q.get("options"):
            print(f"           options: {', '.join(str(o) for o in q['options'][:6])}")
    print()

    # Answer the questionnaire the way a user reasonably would.
    competitors = next(
        (q.get("options", []) for q in task.get("clarifyQuestions") or []
         if q["id"] == "competitors"),
        [],
    )
    submit_clarify(
        task_id,
        {
            "competitors": competitors[:3],
            "focus": ["Feature comparison", "Pricing strategy", "User sentiment"],
            "perspective": "Product manager",
            "market": "United States",
            "user": "SMB teams",
            "freshness": "Within the last year",
        },
    )

    counts: dict[str, int] = {}
    report_id = ""
    error = ""
    async for ev in run_pipeline(task_id):
        etype, data = ev["type"], ev["data"]
        counts[etype] = counts.get(etype, 0) + 1
        if etype == "done":
            report_id = data.get("reportId", "")
        if etype == "error":
            error = data.get("message", "")
        if args.verbose or etype not in _QUIET:
            if etype == "thought":
                print(f"  [{data.get('kind','')}] {data.get('text','')}")
            elif etype == "node_update" and data.get("node"):
                print(f"  <{data['node']}> {data.get('status','')}")
            elif etype == "message":
                print(f"  ({data.get('kind','')}) {data.get('text') or data.get('reason') or ''}")
            elif etype == "progress":
                print(f"  ... {data.get('percent')}% {data.get('stage')} "
                      f"({data.get('evidence_count')} evidence, {data.get('token_used')} tokens)")
            elif etype in ("error", "report_ready", "done"):
                print(f"  {etype}: {data}")

    elapsed = time.monotonic() - t0
    print()
    print(f"finished in {elapsed:.1f}s")
    print("events:", dict(sorted(counts.items())))

    if error:
        print(f"\nFAIL  pipeline reported an error: {error}")
        return 1
    if not report_id:
        print("\nFAIL  pipeline produced no report")
        return 1

    rep = db.get_report(report_id)
    if not rep:
        print(f"\nFAIL  report {report_id} was not persisted")
        return 1

    out_path = args.out or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        f"report-{report_id}.json",
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)

    # ---- invariants -----------------------------------------------------
    evidence = rep.get("evidence", [])
    claims = rep.get("claims", [])
    sections = rep.get("sections", [])
    domains_by_brand: dict[str, set] = {}
    for e in evidence:
        domains_by_brand.setdefault(e.get("brand", ""), set()).add(e.get("domain", ""))

    checks = []
    checks.append(("at least 8 pieces of evidence", len(evidence) >= 8, len(evidence)))
    checks.append(("at least 3 claims", len(claims) >= 3, len(claims)))
    checks.append(
        (
            "every claim carries evidence ids",
            all(c.get("evidence_ids") for c in claims),
            sum(1 for c in claims if not c.get("evidence_ids")),
        )
    )
    checks.append(
        (
            "no claim cites an unknown evidence id",
            all(
                set(c.get("evidence_ids", [])) <= {e["evidence_id"] for e in evidence}
                for c in claims
            ),
            "",
        )
    )
    checks.append(
        (
            "every section has body text",
            all(s.get("paragraphs") for s in sections),
            [s["id"] for s in sections if not s.get("paragraphs")],
        )
    )
    checks.append(("trace spans recorded", len(rep.get("trace", [])) > 0, len(rep.get("trace", []))))
    checks.append(
        (
            "at least one brand has 2+ independent domains",
            any(len(d - {""}) >= 2 for d in domains_by_brand.values()),
            {b: len(d - {""}) for b, d in domains_by_brand.items()},
        )
    )

    print()
    failed = 0
    for label, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {label}  ({detail})")
        failed += 0 if ok else 1

    m = rep.get("metrics", {})
    print()
    print(f"report:   {rep['title']}")
    print(f"          {rep['subtitle']}")
    print(f"sections: {len(sections)} — {', '.join(s['id'] for s in sections)}")
    print(f"charts:   {len(rep.get('charts', []))}")
    print(f"sentiment sample: {rep.get('sentiment', {}).get('sample_size', 0)}")
    print(f"rework:   {rep.get('audit_review', {}).get('rework_rounds', 0)} round(s), "
          f"{rep.get('audit_review', {}).get('issues_resolved', 0)} issue(s) resolved")
    print(f"metrics:  {m.get('efficiency', {}).get('efficiency_multiple')}x efficiency, "
          f"{m.get('coverage', {}).get('independent_sources')} independent sources")
    print(f"saved:    {out_path}")

    print()
    print("PIPELINE PASSED" if failed == 0 else f"PIPELINE FAILED ({failed} check(s))")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
