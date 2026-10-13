"""Database startup compatibility after a code rollback."""
import sqlite3
import threading

import pytest

from app.core import db


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "vantage.db")
    monkeypatch.setattr(db, "_LOCAL", threading.local())
    monkeypatch.setattr(db, "_SCHEMA_READY", False)
    yield db._DB_PATH
    conn = getattr(db._LOCAL, "conn", None)
    if conn is not None:
        conn.close()


def test_fresh_database_and_repeated_initialization(isolated_db):
    db.save_task("t_test", "Example query", {"mode": "quick"})
    conn = db._connect()
    before = list(conn.iterdump())
    db._init_schema(conn)
    assert list(conn.iterdump()) == before
    assert db.get_task("t_test")["query"] == "Example query"
    assert db.list_reports() == []
    assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_legacy_database_still_adds_late_columns(isolated_db):
    conn = sqlite3.connect(isolated_db)
    conn.row_factory = sqlite3.Row
    try:
        db._init_schema(conn)
        for table, names in db._LATE_COLUMNS.items():
            for name in names:
                conn.execute(f"ALTER TABLE {table} DROP COLUMN {name}")
        conn.execute(
            "INSERT INTO reports(report_id, data) VALUES (?, ?)",
            ("r_legacy", '{"mode": "quick"}'),
        )
        conn.commit()
        db._init_schema(conn)
        assert conn.execute("SELECT mode FROM reports").fetchone()[0] == "quick"
        assert {row[1] for row in conn.execute("PRAGMA table_info(tasks)")} >= {
            "terminal_seq", "error"
        }
        assert conn.execute("SELECT starred FROM reports").fetchone()[0] == 0
    finally:
        conn.close()


@pytest.mark.parametrize("version", [2, 3, 4, 5])
def test_versioned_database_rejected_without_changes(version, isolated_db):
    with sqlite3.connect(isolated_db) as conn:
        conn.execute("CREATE TABLE saved_data (value TEXT)")
        conn.execute("INSERT INTO saved_data VALUES ('preserve me')")
        conn.execute(f"PRAGMA user_version={version}")
        conn.commit()
        before = list(conn.iterdump())
        with pytest.raises(db.IncompatibleDatabaseError, match="archive the database"):
            db._init_schema(conn)
        assert list(conn.iterdump()) == before
        assert conn.execute("PRAGMA user_version").fetchone()[0] == version


@pytest.mark.parametrize("table, declaration", [
    ("tasks", "task_id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL"),
    ("reports", "report_id TEXT PRIMARY KEY, current_version_id TEXT"),
    ("evidences", "evidence_id TEXT PRIMARY KEY, data TEXT NOT NULL"),
    ("traces", "span_id TEXT PRIMARY KEY, data TEXT NOT NULL"),
])
def test_newer_structure_without_version_is_rejected(table, declaration, isolated_db):
    with sqlite3.connect(isolated_db) as conn:
        conn.execute(f"CREATE TABLE {table} ({declaration})")
        conn.commit()
        before = list(conn.iterdump())
        with pytest.raises(db.IncompatibleDatabaseError, match="VANTAGE_DB_PATH"):
            db._init_schema(conn)
        assert list(conn.iterdump()) == before


def test_failed_initialization_closes_connection(monkeypatch, isolated_db):
    conn = sqlite3.connect(isolated_db)
    conn.execute("PRAGMA user_version=4")
    monkeypatch.setattr(db.sqlite3, "connect", lambda *args, **kwargs: conn)
    with pytest.raises(db.IncompatibleDatabaseError):
        db._connect()
    assert getattr(db._LOCAL, "conn", None) is None
    assert not db._SCHEMA_READY
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT 1")
