"""Isolated storage and deterministic sources; no model or search network in tests."""
import sqlite3
import threading
from types import SimpleNamespace
import httpx
import pytest
from app.core import db, llm, llm_mock, orchestrator as pipeline, preparation, trace
from app.core.config import Settings

@pytest.fixture
def scope():
    return {"products": [
        {"id": "notion", "name": "Notion", "website": "https://www.notion.com", "category": "Knowledge management software", "own_product": False, "confirmed": True},
        {"id": "obsidian", "name": "Obsidian", "website": "https://obsidian.md", "category": "Knowledge management software", "own_product": False, "confirmed": True}],
        "topics": [{"id": "features", "name": "Features and limitations", "focus": []},
                   {"id": "pricing", "name": "Plans and billing", "focus": []},
                   {"id": "positioning", "name": "Audience and positioning", "focus": []}],
        "changes_days": 90, "scope_acknowledged": False, "limitations": ""}

@pytest.fixture
def offline(monkeypatch, tmp_path):
    settings = Settings(_env_file=None, llm_provider="mock")
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    monkeypatch.setattr(preparation, "get_settings", lambda: settings)
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db, "_LOCAL", threading.local())
    monkeypatch.setattr(db, "_SCHEMA_READY", False)
    connections = []
    original = sqlite3.connect
    def connect(*args, **kwargs):
        conn = original(*args, **kwargs)
        connections.append(conn)
        return conn
    monkeypatch.setattr(db.sqlite3, "connect", connect)
    def network_forbidden(*args, **kwargs):
        pytest.fail("Offline test attempted network access")
    monkeypatch.setattr(httpx.Client, "send", network_forbidden)
    searches, fetches, operations = [], [], []
    def search(query, **kwargs):
        searches.append(query)
        name = "Notion" if "Notion" in query else "Obsidian"
        host = "www.notion.com" if name == "Notion" else "obsidian.md"
        return [{"url": f"https://{host}/pricing", "title": name + " pricing", "snippet": name + " supports offline notes. Pro costs USD 10 per seat per month, billed monthly."}]
    def fetch(url, **kwargs):
        fetches.append((url, kwargs))
        name = "Notion" if "notion" in url else "Obsidian"
        text = name + " supports offline notes. Pro costs USD 10 per seat per month, billed monthly."
        return {"url": url, "text": text, "ok": True, "degraded": False, "captured_at": "2026-10-10T12:00:00Z"}
    monkeypatch.setattr(pipeline, "search", search)
    monkeypatch.setattr(pipeline, "fetch_page", fetch)
    monkeypatch.setattr(preparation, "search", search)
    monkeypatch.setattr(preparation, "fetch_page", fetch)
    original_complete = llm_mock.complete
    def complete(messages, kind, context, json_mode):
        operations.append((kind, context))
        return original_complete(messages, kind, context, json_mode)
    monkeypatch.setattr(llm_mock, "complete", complete)
    from app import main
    from app.core.tasks import TaskRunner
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "runner", TaskRunner())
    monkeypatch.setattr(main, "preparer", preparation.PreparationRunner())
    yield SimpleNamespace(settings=settings, searches=searches, fetches=fetches, operations=operations)
    for conn in connections:
        conn.close()
    trace.clear_context()
