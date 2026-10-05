"""Deterministic collection and isolated SQLite for research/API regressions."""
import sqlite3
import threading
from types import SimpleNamespace

import httpx
import pytest

from app.core import db, llm, llm_mock, orchestrator as pipeline, trace
from app.core.config import Settings
from app.core.platforms import Platform

@pytest.fixture
def offline(monkeypatch, tmp_path):
    settings = Settings(_env_file=None, llm_provider="mock")
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline, "_settings", settings)
    monkeypatch.setattr(llm, "TOKEN_USAGE", {"total": 0})
    monkeypatch.setattr(pipeline, "TOKEN_USAGE", llm.TOKEN_USAGE)
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db, "_LOCAL", threading.local())
    monkeypatch.setattr(db, "_SCHEMA_READY", False)
    connections = []
    original_connect = sqlite3.connect
    def connect(*args, **kwargs):
        conn = original_connect(*args, **kwargs)
        connections.append(conn)
        return conn
    monkeypatch.setattr(db.sqlite3, "connect", connect)
    def network_forbidden(*args, **kwargs):
        pytest.fail("Offline pipeline attempted network access")
    monkeypatch.setattr(httpx.Client, "send", network_forbidden)

    searches, fetches, operations = [], [], []
    def search(queries, **kwargs):
        searches.extend(queries)
        brand = queries[0].split()[0]
        return [{"url": f"https://{brand.lower()}-source-{i}.test/product",
                 "title": f"{brand} documentation {i}",
                 "snippet": f"{brand} documentation explains product feature number {i}. " * 6,
                 "content": f"{brand} documentation explains product feature number {i}. " * 6}
                for i in range(4)]
    def fetch(url, **kwargs):
        fetches.append(url)
        return {"ok": True, "text": kwargs.get("prefetched_text", ""), "images": []}
    def comments(brand, category, limit):
        return [{"text": f"I love {brand}; this product is great for our team.",
                 "url": f"https://news.ycombinator.com/item?id={brand}", "title": f"{brand} review"},
                {"text": f"{brand} is expensive and slow for our workflow.",
                 "url": f"https://news.ycombinator.com/item?id={brand}-negative", "title": f"{brand} review"}]
    monkeypatch.setattr(pipeline, "multi_search", search)
    monkeypatch.setattr(pipeline, "fetch_page", fetch)
    platform = Platform("hackernews", "Hacker News", "news.ycombinator.com", "hackernews", collector=comments)
    monkeypatch.setattr(pipeline, "api_platforms", lambda: [platform])
    monkeypatch.setattr(pipeline, "search_platforms", lambda: [])
    original_complete = llm_mock.complete
    def complete(messages, kind, context, json_mode):
        operations.append((kind, context))
        return original_complete(messages, kind, context, json_mode)
    monkeypatch.setattr(llm_mock, "complete", complete)
    from app import main
    from app.core.tasks import TaskRunner
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "runner", TaskRunner())
    monkeypatch.setattr(pipeline, "public_addresses", lambda url: ["93.184.216.34"])
    yield SimpleNamespace(searches=searches, fetches=fetches, operations=operations)
    for conn in connections:
        conn.close()
    trace.set_context("", "", "", "")


