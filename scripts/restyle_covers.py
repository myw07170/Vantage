"""Rewrite the stored cover image of every saved report.

The cover is generated art, derived from nothing but the report id, so it can be
recomputed at any time — which makes a change to `_cover_image` a backfill rather
than a migration. Reports written before the change keep whatever the generator
produced on the day they ran; this brings them into line.

The cover is held twice: the `cover_image` column, which the library grid reads,
and inside the `data` JSON blob, which the report page reads. Both are rewritten,
or the two views would disagree.

    uv run python scripts/restyle_covers.py --dry-run   # report, change nothing
    uv run python scripts/restyle_covers.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.core import db  # noqa: E402
from app.core.orchestrator import _cover_image  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    args = ap.parse_args()

    with db._LOCK:
        conn = db._connect()
        rows = conn.execute("SELECT report_id, cover_image, data FROM reports").fetchall()

        changed = 0
        for row in rows:
            rid = row["report_id"]
            cover = _cover_image(rid)
            if row["cover_image"] == cover:
                continue
            changed += 1
            print(f"  {rid}")
            if args.dry_run:
                continue

            # The blob is the report page's source of truth; a row whose blob is
            # unreadable still gets its column fixed rather than aborting the run.
            data = row["data"]
            try:
                report = json.loads(data)
                report["cover_image"] = cover
                data = json.dumps(report)
            except (ValueError, TypeError) as exc:
                print(f"    ! blob left as-is, could not parse: {exc}")

            conn.execute(
                "UPDATE reports SET cover_image=?, data=? WHERE report_id=?",
                (cover, data, rid),
            )

        if not args.dry_run:
            conn.commit()

    total = len(rows)
    verb = "would be restyled" if args.dry_run else "restyled"
    print(f"\n{changed} of {total} report(s) {verb}.")
    if args.dry_run and changed:
        print("Re-run without --dry-run to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
