"""Run one confirmed comparison headlessly; real model calls require --allow-live."""
from __future__ import annotations
import argparse
import asyncio
import json
import hashlib
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core import db
from app.core.config import get_settings
from app.core.models import DEFAULT_TOPICS, ResearchScope, all_items
from app.core.tasks import TaskRunner

async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", type=Path, help="JSON ResearchScope with explicitly confirmed product identities.")
    parser.add_argument("--query", default="Notion vs Obsidian for a small research team")
    parser.add_argument("--allow-live", action="store_true", help="Allow real model calls using the configured provider.")
    parser.add_argument("--out", type=Path, default=Path(".run-logs/comparison.json"))
    args = parser.parse_args()
    settings = get_settings()
    config_path = Path(__file__).resolve().parents[1] / "backend" / ".env"
    config_digest = hashlib.sha256(config_path.read_bytes()).digest() if config_path.exists() else None
    if not settings.is_mock and not args.allow_live:
        parser.error("Real inference requires --allow-live; configure LLM_PROVIDER=mock for simulated inference.")
    if not settings.llm_configured:
        parser.error(settings.llm_configuration_error)
    data = json.loads(args.scope.read_text(encoding="utf-8")) if args.scope else {
        "products": [
            {"id": "notion", "name": "Notion", "website": "https://www.notion.com", "category": "Knowledge management software", "own_product": False, "confirmed": True},
            {"id": "obsidian", "name": "Obsidian", "website": "https://obsidian.md", "category": "Knowledge management software", "own_product": False, "confirmed": True}],
        "topics": DEFAULT_TOPICS, "changes_days": 90, "scope_acknowledged": False, "limitations": ""}
    scope = ResearchScope.model_validate(data)
    db.initialize()
    db.interrupt_running_tasks()
    runner = TaskRunner()
    task = db.save_task(args.query, payload={"scope": scope.model_dump()})
    print(json.dumps({"task_id": task["task_id"], "provider": settings.llm_provider,
                      "model": settings.llm_model_core, "token_limit": settings.research_token_limit,
                      "time_limit_seconds": settings.research_time_limit_seconds}), flush=True)
    runner.start(task["task_id"])
    try:
        async for event in runner.subscribe(task["task_id"]):
            if event["type"] not in ("evidence", "heartbeat"):
                print(json.dumps({"event": event["type"], **event["data"]}, ensure_ascii=True), flush=True)
        task = db.get_task(task["task_id"])
        version = db.get_version(task["report_id"], task["version_id"]) if task["version_id"] else None
        content = version["content"] if version else task["checkpoint"].get("content", {})
        summary = {
            "task_id": task["task_id"], "status": task["status"], "report_id": task["report_id"],
            "version_id": task["version_id"], "provider": settings.llm_provider, "model": settings.llm_model_core,
            "evidence_count": len(content.get("evidence", [])), "item_count": len(all_items(content)),
            "review_summary": content.get("review_summary", {}), "limitations": content.get("limitations", []),
            "usage": task["checkpoint"].get("usage", {}), "error": task["error"],
            "configuration_unchanged": (hashlib.sha256(config_path.read_bytes()).digest() if config_path.exists() else None) == config_digest,
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(version or task, ensure_ascii=False, indent=2), encoding="utf-8")
        args.out.with_suffix(".summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print("RESULT " + json.dumps(summary, ensure_ascii=True), flush=True)
        return 0 if task["status"] == "done" else 1
    finally:
        await runner.close()

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
