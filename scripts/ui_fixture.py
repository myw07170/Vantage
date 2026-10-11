"""Offline UI smoke-test server. Never touches the normal database or model network."""
from __future__ import annotations
import datetime as dt
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ["VANTAGE_DB_PATH"] = os.environ.get("VANTAGE_UI_DB_PATH", str(Path(__file__).resolve().parents[1] / ".run-logs" / "ui-fixture.db"))
from app import main
from app.core import db, llm, orchestrator, preparation
from app.core.config import Settings
from app.core.models import DEFAULT_TOPICS, ReportContent, ReportItem, now
from app.core.review import apply_reviews
import uvicorn

settings = Settings(_env_file=None, llm_provider="mock")
main.settings = settings
llm.get_settings = lambda: settings
orchestrator.get_settings = lambda: settings
preparation.get_settings = lambda: settings
def search(query, **kwargs):
    product = "Notion" if "Notion" in query else "Obsidian"
    host = "www.notion.com" if product == "Notion" else "obsidian.md"
    return [{"url": f"https://{host}/pricing", "title": product + " pricing", "snippet": product + " supports offline notes. Pro costs USD 10 per seat per month, billed monthly."}]
def fetch(url, **kwargs):
    product = "Notion" if "notion" in url else "Obsidian"
    return {"url": url, "text": product + " supports offline notes. Pro costs USD 10 per seat per month, billed monthly.", "captured_at": now(), "ok": True, "degraded": False}
orchestrator.search = search
orchestrator.fetch_page = fetch
preparation.search = search
preparation.fetch_page = fetch

db.initialize()
@main.app.get('/api/fixture-health')
def fixture_health():
    return {'offline_fixture': True}

if not db.list_reports():
    products = [
        {"id": "notion", "name": "Notion", "website": "https://www.notion.com", "category": "Knowledge management software", "own_product": False, "confirmed": True},
        {"id": "obsidian", "name": "Obsidian", "website": "https://obsidian.md", "category": "Knowledge management software", "own_product": False, "confirmed": True}]
    content = ReportContent(products=products, topics=DEFAULT_TOPICS, checked_at=now(),
                            changes_since=(dt.date.today() - dt.timedelta(days=90)).isoformat(), is_mock=True, llm_provider="mock").model_dump()
    for p in products:
        text = p["name"] + " supports offline notes. Pro costs USD 10 per seat per month, billed monthly."
        content["evidence"].append({"evidence_id": "ev-" + p["id"], "product_id": p["id"], "topic_id": "features",
            "source_url": p["website"] + "/pricing", "source_type": "official", "attribution": "Fixture vendor source.",
            "title": p["name"] + " documentation", "excerpt": text, "context": text, "captured_at": now(),
            "published_at": None, "published_date_basis": "", "degraded": False, "limitation": ""})
        for t in DEFAULT_TOPICS:
            content["comparison"].append(ReportItem(id=p["id"] + "-" + t["id"], product_id=p["id"], topic_id=t["id"],
                text="[FIXTURE] " + text, citations=[{"evidence_id": "ev-" + p["id"], "quote": text}]).model_dump())
    content["brief"] = [ReportItem(id="brief-1", kind="inference", text="[FIXTURE] Both supplied sources describe monthly per-seat pricing; assess plan eligibility before choosing.",
        citations=content["comparison"][0]["citations"], depends_on=["notion-pricing", "obsidian-pricing"]).model_dump()]
    for kind, title, host in [("external", "[FIXTURE] Public user report", "reviews.example"), ("unknown", "[FIXTURE] Unattributed pricing note", "unattributed.example")]:
        content["evidence"].append({**content["evidence"][0], "evidence_id": "ev-" + kind,
            "source_type": kind, "source_url": f"https://{host}/notes", "title": title,
            "attribution": "Offline fixture only.", "limitation": "Source ownership is not established." if kind == "unknown" else "Individual experience; may not apply to all plans."})
    items = content["comparison"] + content["brief"]
    apply_reviews(content, items, {"reviews": [{"item_id": i["id"], "status": "supported", "reason": "Fixed test data only; not an actual product conclusion.",
                                              "evidence_ids": [r["evidence_id"] for r in i["citations"]], "quotes": i["citations"]} for i in items]})
    db.create_version(None, content, "research", title="Notion vs Obsidian - offline UI fixture")
uvicorn.run(main.app, host="127.0.0.1", port=int(os.environ.get("VANTAGE_UI_PORT", "8010")), log_level="warning")
