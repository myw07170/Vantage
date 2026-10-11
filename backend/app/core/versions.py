"""Immutable report snapshots and optimistic current-version protection."""
from __future__ import annotations
import copy
from app.core import db
from app.core.models import all_items
from app.core.review import invalidate

def require_version(report_id: str, version_id: str) -> dict:
    version = db.get_version(report_id, version_id)
    if not version:
        raise KeyError("Report version not found.")
    return version

def edit(report_id: str, base_version_id: str, edits: dict[str, str]) -> dict:
    base = require_version(report_id, base_version_id)
    content = copy.deepcopy(base["content"])
    items = {i["id"]: i for i in all_items(content)}
    if not edits or any(k not in items or not text.strip() or len(text) > 20000 for k, text in edits.items()):
        raise ValueError("Provide nonempty edits for existing report items, up to 20,000 characters each.")
    changed = {k for k, text in edits.items() if items[k]["text"] != text.strip()}
    if not changed:
        raise ValueError("There are no content changes to save.")
    for key in changed:
        items[key]["text"] = edits[key].strip()
    affected = invalidate(content, changed)
    return db.create_version(report_id, content, "manual", base_version_id=base_version_id,
                             metadata={"edits": edits, "affected_ids": sorted(affected),
                                       "source_task_id": base["task_id"] or base["metadata"].get("source_task_id", "")})

def apply(report_id: str, base_version_id: str, candidate_version_id: str) -> dict:
    candidate = require_version(report_id, candidate_version_id)
    if candidate["state"] != "candidate":
        raise ValueError("Select a candidate version to apply.")
    if candidate["base_version_id"] != base_version_id:
        raise db.Conflict("This candidate was researched from a different base version. Start a new follow-up from the current report.")
    return db.create_version(report_id, candidate["content"], "apply", base_version_id=base_version_id,
                             metadata={"candidate_version_id": candidate_version_id, **candidate["metadata"], "source_task_id": candidate["task_id"]})

def restore(report_id: str, base_version_id: str, version_id: str) -> dict:
    source = require_version(report_id, version_id)
    if source["state"] != "applied":
        raise ValueError("Candidates must be applied through the candidate preview.")
    return db.create_version(report_id, source["content"], "restore", base_version_id=base_version_id,
                             metadata={"restored_from": version_id, "source_task_id": source["task_id"] or source["metadata"].get("source_task_id", "")})
