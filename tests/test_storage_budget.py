"""One-time transactional legacy reset and hard per-task resource controls."""
import sqlite3
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from app.core import budget, db, llm, ratelimit
from app.core.config import Settings

def test_legacy_reset_once_and_new_data_survives(offline, tmp_path):
    conn = sqlite3.connect(db._DB_PATH)
    conn.execute("CREATE TABLE reports (id TEXT)")
    conn.execute("INSERT INTO reports VALUES('legacy')")
    conn.execute("CREATE TABLE subscriptions (id TEXT)")
    conn.commit()
    conn.close()
    config = tmp_path / ".env"
    config.write_text("LLM_PROVIDER=qwen\nQWEN_API_KEY=do-not-touch", encoding="utf-8")
    db.initialize()
    assert db.list_reports() == []
    tid = db.save_task("new comparison")["task_id"]
    conn = sqlite3.connect(db._DB_PATH)
    db._init_schema(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    assert conn.execute("SELECT task_id FROM tasks").fetchone()[0] == tid
    assert not conn.execute("SELECT name FROM sqlite_master WHERE name='subscriptions'").fetchone()
    assert config.read_text(encoding="utf-8").endswith("QWEN_API_KEY=do-not-touch")
    conn.close()

def test_failed_schema_initialization_rolls_back_old_data(tmp_path):
    class FailingConnection(sqlite3.Connection):
        fail = False
        def execute(self, sql, *args, **kwargs):
            if self.fail and sql.startswith("CREATE TABLE versions"):
                raise sqlite3.OperationalError("simulated DDL failure")
            return super().execute(sql, *args, **kwargs)
    conn = sqlite3.connect(tmp_path / "failure.db", factory=FailingConnection)
    conn.execute("CREATE TABLE reports (id TEXT)")
    conn.execute("INSERT INTO reports VALUES('keep-on-failure')")
    conn.commit()
    conn.fail = True
    with pytest.raises(sqlite3.OperationalError):
        db._init_schema(conn)
    assert conn.execute("SELECT id FROM reports").fetchone()[0] == "keep-on-failure"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    conn.close()

def test_newer_database_is_not_destroyed(tmp_path):
    conn = sqlite3.connect(tmp_path / "future.db")
    conn.execute("PRAGMA user_version=99")
    with pytest.raises(RuntimeError, match="newer"):
        db._init_schema(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 99
    conn.close()

def test_concurrent_current_version_mutations_only_one_wins(offline):
    base = db.create_version(None, {"data": "base"}, "research")
    def change(number):
        try:
            return db.create_version(base["report_id"], {"data": number}, "manual", base_version_id=base["version_id"])["version_id"]
        except db.Conflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(change, [1, 2]))
    assert results.count("conflict") == 1
    assert len(db.list_versions(base["report_id"])) == 2

@pytest.fixture
def provider(monkeypatch):
    settings = Settings(_env_file=None, llm_provider="qwen", qwen_api_key="test-only", llm_max_retries=1)
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "_limiter_ready", False)
    monkeypatch.setattr(ratelimit, "limiter", ratelimit.RateLimiter())
    yield settings

def test_budget_reserves_before_call(provider, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "_client", httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r))))
    b = budget.Budget(10, 10)
    token = budget.CURRENT.set(b)
    try:
        with pytest.raises(budget.BudgetExceeded, match="Insufficient"):
            llm.chat([{"role": "user", "content": "some input"}], max_tokens=20)
        assert calls == []
    finally:
        budget.CURRENT.reset(token)
        llm._client.close()

@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}])
def test_missing_usage_conservatively_charged_and_timeout_bounded(provider, monkeypatch, usage):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ready"}, "finish_reason": "stop"}], "usage": usage})
    monkeypatch.setattr(llm, "_client", httpx.Client(transport=httpx.MockTransport(respond)))
    b = budget.Budget(1000, 3)
    token = budget.CURRENT.set(b)
    try:
        assert llm.chat([{"role": "user", "content": "hello"}], max_tokens=100) == "ready"
        assert b.used >= 100 and b.estimated
        assert calls[0].extensions["timeout"]["read"] <= 3
    finally:
        budget.CURRENT.reset(token)
        llm._client.close()

def test_failed_attempts_count_against_task_budget(provider, monkeypatch):
    calls = []
    def fail(request):
        calls.append(request)
        return httpx.Response(503, json={})
    monkeypatch.setattr(llm, "_client", httpx.Client(transport=httpx.MockTransport(fail)))
    monkeypatch.setattr(ratelimit, "backoff_delay", lambda *a: 0)
    b = budget.Budget(1000, 3)
    token = budget.CURRENT.set(b)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            llm.chat([{"role": "user", "content": "hello"}], max_tokens=100)
        assert len(calls) == 2 and b.used >= 200 and b.estimated
    finally:
        budget.CURRENT.reset(token)
        llm._client.close()

def test_rate_limit_wait_obeys_task_deadline():
    limiter = ratelimit.RateLimiter()
    limiter.configure("core", rpm=1, rpd=0, tpm=0, max_concurrency=1)
    with ratelimit.slot(limiter, "core", 1):
        pass
    b = budget.Budget(100, 0.03)
    token = budget.CURRENT.set(b)
    started = time.monotonic()
    try:
        with pytest.raises(budget.BudgetExceeded):
            with ratelimit.slot(limiter, "core", 1):
                pass
        assert time.monotonic() - started < 0.3
    finally:
        budget.CURRENT.reset(token)

def test_cancelled_budget_prevents_new_work():
    b = budget.Budget(100, 10)
    b.cancelled.set()
    with pytest.raises(budget.BudgetExceeded):
        b.reserve(1)
