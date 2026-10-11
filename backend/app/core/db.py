"""Transactional SQLite storage; legacy data is reset exactly once at schema v2."""
from __future__ import annotations
import json
import os
import sqlite3
import threading
import uuid
from pathlib import Path
from app.core.models import now

_DB_PATH = Path(os.environ.get("VANTAGE_DB_PATH") or Path(__file__).resolve().parent.parent / "data" / "vantage.db")
_LOCK = threading.RLock()
_LOCAL = threading.local()
_SCHEMA_READY = False
SCHEMA_VERSION = 3

def uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"

class Conflict(ValueError):
    pass

def _connect() -> sqlite3.Connection:
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            _init_schema(conn)
        except BaseException:
            conn.close()
            raise
        _LOCAL.conn = conn
    return conn

def _init_schema(conn: sqlite3.Connection) -> None:
    global _SCHEMA_READY
    with _LOCK:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError("Database is newer than this application; startup stopped.")
        if version == SCHEMA_VERSION:
            _SCHEMA_READY = True
            return
        # DDL and the version marker commit together, without executescript's implicit commit.
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            for table in (() if version == 2 else ("report_feedback", "traces", "evidences", "subscriptions", "expert_stats",
                          "tasks", "reports")):
                conn.execute(f"DROP TABLE IF EXISTS {table}")
            statements = [
                "CREATE TABLE tasks (task_id TEXT PRIMARY KEY, kind TEXT NOT NULL, query TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, report_id TEXT, version_id TEXT, terminal_seq INTEGER DEFAULT 0, error TEXT DEFAULT '', checkpoint TEXT DEFAULT '{}')",
                "CREATE TABLE reports (report_id TEXT PRIMARY KEY, title TEXT NOT NULL, current_version_id TEXT, starred INTEGER DEFAULT 0, created_at TEXT NOT NULL)",
                "CREATE TABLE versions (version_id TEXT PRIMARY KEY, report_id TEXT NOT NULL REFERENCES reports(report_id) ON DELETE CASCADE, base_version_id TEXT, kind TEXT NOT NULL, state TEXT NOT NULL, task_id TEXT, metadata TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)",
                "CREATE TABLE evidences (evidence_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, report_id TEXT, data TEXT NOT NULL)",
                "CREATE TABLE traces (span_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, report_id TEXT, seq INTEGER, data TEXT NOT NULL)",
                "CREATE INDEX idx_versions_report ON versions(report_id, created_at)",
                "CREATE INDEX idx_evidences_task ON evidences(task_id)",
                "CREATE INDEX idx_traces_task ON traces(task_id, seq)",
                "CREATE INDEX idx_tasks_created ON tasks(created_at DESC)",
            ]
            for statement in ([] if version == 2 else statements):
                conn.execute(statement)
            conn.execute("CREATE TABLE annotations (annotation_id TEXT PRIMARY KEY, report_id TEXT NOT NULL REFERENCES reports(report_id) ON DELETE CASCADE, version_id TEXT NOT NULL REFERENCES versions(version_id) ON DELETE CASCADE, data TEXT NOT NULL)")
            conn.execute("CREATE INDEX idx_annotations_version ON annotations(report_id, version_id)")
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        _SCHEMA_READY = True

def initialize() -> None:
    _connect()

def save_task(query: str, kind: str = "research", payload: dict | None = None, report_id: str | None = None) -> dict:
    tid = uid("t")
    with _LOCK, _connect() as c:
        c.execute("INSERT INTO tasks(task_id,kind,query,payload,status,created_at,report_id) VALUES(?,?,?,?,?,?,?)",
                  (tid, kind, query, json.dumps(payload or {}), "created", now(), report_id))
    return get_task(tid)

def get_task(task_id: str) -> dict | None:
    row = _connect().execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    for key in ("payload", "checkpoint"):
        data[key] = json.loads(data[key])
    return data

def list_tasks() -> list[dict]:
    rows = _connect().execute("SELECT task_id FROM tasks ORDER BY created_at DESC").fetchall()
    return [get_task(row[0]) for row in rows]

def claim_task(task_id: str, payload: dict | None = None) -> bool:
    with _LOCK, _connect() as c:
        if payload is None:
            row = c.execute("UPDATE tasks SET status='running' WHERE task_id=? AND status IN ('created','awaiting_confirmation')", (task_id,))
        else:
            row = c.execute("UPDATE tasks SET status='running',payload=? WHERE task_id=? AND status IN ('created','awaiting_confirmation')",
                            (json.dumps(payload), task_id))
        return row.rowcount == 1

def checkpoint(task_id: str, data: dict) -> None:
    with _LOCK, _connect() as c:
        c.execute("UPDATE tasks SET checkpoint=? WHERE task_id=? AND status IN ('running','done','failed','interrupted')", (json.dumps(data), task_id))

def finish_task(task_id: str, status: str, seq: int, error: str = "") -> None:
    with _LOCK, _connect() as c:
        c.execute("UPDATE tasks SET status=?,terminal_seq=?,error=? WHERE task_id=?", (status, seq, error, task_id))

def interrupt_running_tasks() -> None:
    with _LOCK, _connect() as c:
        c.execute("UPDATE tasks SET status='interrupted',terminal_seq=MAX(terminal_seq,1),error=? WHERE status='running'",
                  ("Interrupted by a backend restart. Retry manually to create a new task.",))
        for row in c.execute("SELECT task_id,payload FROM tasks WHERE status='preparing'").fetchall():
            payload = json.loads(row[1])
            payload['preparation']['status'] = 'interrupted'
            c.execute("UPDATE tasks SET status='awaiting_confirmation',payload=? WHERE task_id=?", (json.dumps(payload), row[0]))

def save_evidence(task_id: str, evidence: dict, report_id: str | None = None) -> None:
    with _LOCK, _connect() as c:
        c.execute("INSERT OR IGNORE INTO evidences VALUES(?,?,?,?)",
                  (evidence["evidence_id"], task_id, report_id, json.dumps(evidence)))

def save_traces(task_id: str, report_id: str, spans: list[dict]) -> None:
    with _LOCK, _connect() as c:
        for span in spans:
            c.execute("INSERT OR REPLACE INTO traces VALUES(?,?,?,?,?)",
                      (span["span_id"], task_id, report_id, span.get("seq", 0), json.dumps(span)))

def get_traces_by_task(task_id: str) -> list[dict]:
    return [json.loads(r[0]) for r in _connect().execute("SELECT data FROM traces WHERE task_id=? ORDER BY seq", (task_id,))]

def get_traces_by_report(report_id: str) -> list[dict]:
    return [json.loads(r[0]) for r in _connect().execute("SELECT data FROM traces WHERE report_id=? ORDER BY seq", (report_id,))]

def _version(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    data = dict(row)
    data["metadata"] = json.loads(data["metadata"])
    data["content"] = json.loads(data["content"])
    return data

def get_version(report_id: str, version_id: str) -> dict | None:
    return _version(_connect().execute("SELECT * FROM versions WHERE report_id=? AND version_id=?", (report_id, version_id)).fetchone())

def get_report(report_id: str) -> dict | None:
    row = _connect().execute("SELECT * FROM reports WHERE report_id=?", (report_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    data["starred"] = bool(data["starred"])
    data["version"] = get_version(report_id, data["current_version_id"])
    return data

def list_reports() -> list[dict]:
    rows = _connect().execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall()
    return [{**dict(row), "starred": bool(row["starred"])} for row in rows]

def list_versions(report_id: str) -> list[dict]:
    rows = _connect().execute("SELECT * FROM versions WHERE report_id=? ORDER BY created_at DESC,rowid DESC", (report_id,)).fetchall()
    return [{k: v for k, v in _version(row).items() if k != "content"} for row in rows]

def create_version(report_id: str | None, content: dict, kind: str, *, base_version_id: str | None = None,
                   candidate: bool = False, task_id: str = "", metadata: dict | None = None, title: str = "") -> dict:
    vid, rid = uid("v"), report_id or uid("r")
    with _LOCK, _connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if not report_id:
            c.execute("INSERT INTO reports VALUES(?,?,?,?,?)", (rid, title or "Product comparison", None, 0, now()))
        row = c.execute("SELECT current_version_id FROM reports WHERE report_id=?", (rid,)).fetchone()
        if not row:
            raise KeyError("Report not found.")
        if not candidate and row[0] != base_version_id:
            raise Conflict("The current version changed. Reload and review your changes before applying.")
        c.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?,?,?)",
                  (vid, rid, base_version_id, kind, "candidate" if candidate else "applied", task_id,
                   json.dumps(metadata or {}), json.dumps(content), now()))
        from app.core.annotations import inherit
        source_id = (metadata or {}).get('restored_from') if kind == 'restore' else base_version_id
        if source_id:
            inherit(c, rid, source_id, vid, content)
        if not candidate:
            c.execute("UPDATE reports SET current_version_id=? WHERE report_id=?", (vid, rid))
        if task_id:
            c.execute("UPDATE tasks SET report_id=?,version_id=? WHERE task_id=?", (rid, vid, task_id))
            c.execute("UPDATE evidences SET report_id=? WHERE task_id=?", (rid, task_id))
            c.execute("UPDATE traces SET report_id=? WHERE task_id=?", (rid, task_id))
    return get_version(rid, vid)

def update_report(report_id: str, title: str | None = None, starred: bool | None = None) -> dict | None:
    with _LOCK, _connect() as c:
        if title is not None:
            c.execute("UPDATE reports SET title=? WHERE report_id=?", (title, report_id))
        if starred is not None:
            c.execute("UPDATE reports SET starred=? WHERE report_id=?", (int(starred), report_id))
    return get_report(report_id)

def delete_report(report_id: str) -> bool:
    with _LOCK, _connect() as c:
        active = c.execute("SELECT 1 FROM tasks WHERE report_id=? AND status='running'", (report_id,)).fetchone()
        if active:
            raise Conflict("Wait for this report's active tasks before deleting it.")
        for table in ("evidences", "traces", "tasks"):
            c.execute(f"DELETE FROM {table} WHERE report_id=?", (report_id,))
        return c.execute("DELETE FROM reports WHERE report_id=?", (report_id,)).rowcount == 1
