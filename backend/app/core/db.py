"""SQLite persistence: tasks, reports, evidence, subscriptions, expert stats, traces.

Everything goes through here — no in-memory dict is ever the source of truth,
so navigating away, refreshing or restarting never loses work.

Concurrency note: the orchestrator spawns many worker threads via
`asyncio.to_thread`, and a single `sqlite3.Connection` shared across them
deadlocks ("recursive use of cursors", which surfaces as a hung backend). Each
thread therefore gets its own connection, with WAL mode plus a busy timeout so
concurrent writers queue instead of erroring.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


def _resolve_db_path() -> Path:
    """Where the database file lives.

    Local: `app/data/vantage.db`. On a serverless host the filesystem is
    read-only apart from /tmp, which lasts only for the function's lifetime.
    `VANTAGE_DB_PATH` overrides both.
    """
    override = os.environ.get("VANTAGE_DB_PATH")
    if override:
        return Path(override)
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return Path("/tmp/vantage.db")
    return Path(__file__).resolve().parent.parent / "data" / "vantage.db"


_DB_PATH = _resolve_db_path()
# SQLite allows one writer at a time; serializing writes avoids "database is locked".
_LOCK = threading.RLock()
_LOCAL = threading.local()
_SCHEMA_READY = False
_SCHEMA_LOCK = threading.Lock()


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _connect() -> sqlite3.Connection:
    conn = getattr(_LOCAL, "conn", None)
    if conn is not None:
        return conn
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
    except sqlite3.Error:
        pass
    _ensure_schema(conn)
    _LOCAL.conn = conn
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        _init_schema(conn)
        _SCHEMA_READY = True


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            query TEXT,
            clarifications TEXT,
            status TEXT,
            created_at TEXT,
            report_id TEXT
        );
        CREATE TABLE IF NOT EXISTS reports (
            report_id TEXT PRIMARY KEY,
            task_id TEXT,
            title TEXT,
            subtitle TEXT,
            query TEXT,
            brands TEXT,
            experts TEXT,
            cover_image TEXT,
            data TEXT,
            evidence_count INTEGER,
            claim_count INTEGER,
            high_conf_count INTEGER,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS evidences (
            evidence_id TEXT PRIMARY KEY,
            report_id TEXT,
            source_url TEXT,
            source_type TEXT,
            domain TEXT,
            title TEXT,
            excerpt TEXT,
            credibility REAL,
            collected_by TEXT,
            brand TEXT,
            captured_at TEXT
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            sub_id TEXT PRIMARY KEY,
            query TEXT,
            brands TEXT,
            created_at TEXT,
            last_run_at TEXT,
            last_report_id TEXT,
            run_count INTEGER
        );
        CREATE TABLE IF NOT EXISTS expert_stats (
            expert_id TEXT PRIMARY KEY,
            missions INTEGER DEFAULT 0,
            claims_authored INTEGER DEFAULT 0,
            evidence_collected INTEGER DEFAULT 0,
            last_active TEXT
        );
        CREATE TABLE IF NOT EXISTS traces (
            span_id TEXT PRIMARY KEY,
            task_id TEXT,
            report_id TEXT,
            seq INTEGER,
            agent_id TEXT,
            stage TEXT,
            purpose TEXT,
            model TEXT,
            prompt TEXT,
            response TEXT,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            latency_ms INTEGER,
            decision TEXT,
            evidence_ids TEXT,
            ts TEXT
        );
        CREATE TABLE IF NOT EXISTS report_feedback (
            report_id TEXT PRIMARY KEY,
            edited_blocks INTEGER,
            total_blocks INTEGER,
            data TEXT,
            updated_at TEXT
        );

        -- Every hot read filters on one of these; without them the evidence
        -- library and trace views degrade to full scans as history grows.
        CREATE INDEX IF NOT EXISTS idx_evidences_report ON evidences(report_id);
        CREATE INDEX IF NOT EXISTS idx_evidences_brand ON evidences(brand);
        CREATE INDEX IF NOT EXISTS idx_evidences_type ON evidences(source_type);
        CREATE INDEX IF NOT EXISTS idx_traces_task ON traces(task_id, seq);
        CREATE INDEX IF NOT EXISTS idx_traces_report ON traces(report_id, seq);
        CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at DESC);
        """
    )
    conn.commit()


# ── tasks ─────────────────────────────────────────────────────────────────────
def save_task(task_id: str, query: str, clarifications: Dict[str, Any]) -> None:
    with _LOCK:
        c = _connect()
        c.execute(
            "INSERT OR REPLACE INTO tasks(task_id,query,clarifications,status,created_at,report_id)"
            " VALUES(?,?,?,?,?,COALESCE((SELECT report_id FROM tasks WHERE task_id=?),NULL))",
            (task_id, query, json.dumps(clarifications), "created", _now(), task_id),
        )
        c.commit()


def update_task_clarify(task_id: str, clarifications: Dict[str, Any]) -> None:
    with _LOCK:
        c = _connect()
        c.execute(
            "UPDATE tasks SET clarifications=?, status='clarified' WHERE task_id=?",
            (json.dumps(clarifications), task_id),
        )
        c.commit()


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    c = _connect()
    row = c.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["clarifications"] = json.loads(d.get("clarifications") or "{}")
    return d


def mark_task_done(task_id: str, report_id: str) -> None:
    with _LOCK:
        c = _connect()
        c.execute(
            "UPDATE tasks SET status='done', report_id=? WHERE task_id=?",
            (report_id, task_id),
        )
        c.commit()


# ── reports + evidence ────────────────────────────────────────────────────────
def save_report(report: Dict[str, Any], task_id: str = "") -> None:
    evidence = report.get("evidence", [])
    claims = report.get("claims", [])
    high = sum(1 for c in claims if c.get("confidence") == "high")
    with _LOCK:
        c = _connect()
        c.execute(
            "INSERT OR REPLACE INTO reports(report_id,task_id,title,subtitle,query,brands,experts,"
            "cover_image,data,evidence_count,claim_count,high_conf_count,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                report["id"],
                task_id,
                report.get("title", ""),
                report.get("subtitle", ""),
                report.get("query", ""),
                json.dumps(report.get("brands", [])),
                json.dumps(report.get("experts", [])),
                report.get("cover_image", ""),
                json.dumps(report),
                len(evidence),
                len(claims),
                high,
                report.get("created_at", _now()),
            ),
        )
        # Evidence is also stored row-wise so the global evidence library can
        # query across every report, not just inside one report's JSON blob.
        for ev in evidence:
            c.execute(
                "INSERT OR REPLACE INTO evidences(evidence_id,report_id,source_url,source_type,"
                "domain,title,excerpt,credibility,collected_by,brand,captured_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ev.get("evidence_id"),
                    report["id"],
                    ev.get("source_url", ""),
                    ev.get("source_type", ""),
                    ev.get("domain", ""),
                    ev.get("title", ""),
                    ev.get("excerpt", "")[:500],
                    ev.get("credibility", 0.0),
                    ev.get("collected_by", ""),
                    ev.get("brand", ""),
                    ev.get("captured_at", _now()),
                ),
            )
        c.commit()


def get_report(report_id: str) -> Optional[Dict[str, Any]]:
    c = _connect()
    row = c.execute(
        "SELECT data FROM reports WHERE report_id=?", (report_id,)
    ).fetchone()
    if not row:
        return None
    return json.loads(row["data"])


def list_reports() -> List[Dict[str, Any]]:
    """Report cards — omits the full `data` blob to keep the list light."""
    c = _connect()
    rows = c.execute(
        "SELECT report_id,title,subtitle,query,brands,experts,cover_image,"
        "evidence_count,claim_count,high_conf_count,created_at FROM reports "
        "ORDER BY created_at DESC"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["id"] = d["report_id"]
        d["brands"] = json.loads(d.get("brands") or "[]")
        d["experts"] = json.loads(d.get("experts") or "[]")
        out.append(d)
    return out


def delete_report(report_id: str) -> bool:
    """
    Remove a report and everything derived from it. Returns False if unknown.

    The cascade is explicit because no table declares a foreign key. It has to
    be: orphaned evidence rows would keep inflating the dashboard counts and the
    global evidence library long after the report they came from is gone, and an
    orphaned `last_report_id` would leave a subscription linking to a 404.

    The task row survives as history — only its dangling report link is cleared.
    """
    with _LOCK:
        c = _connect()
        hit = c.execute(
            "SELECT 1 FROM reports WHERE report_id=?", (report_id,)
        ).fetchone()
        if not hit:
            return False
        c.execute("DELETE FROM reports WHERE report_id=?", (report_id,))
        c.execute("DELETE FROM evidences WHERE report_id=?", (report_id,))
        c.execute("DELETE FROM traces WHERE report_id=?", (report_id,))
        c.execute("DELETE FROM report_feedback WHERE report_id=?", (report_id,))
        c.execute("UPDATE tasks SET report_id='' WHERE report_id=?", (report_id,))
        c.execute(
            "UPDATE subscriptions SET last_report_id='' WHERE last_report_id=?",
            (report_id,),
        )
        c.commit()
        return True


# ── global evidence library ───────────────────────────────────────────────────
def query_evidences(
    brand: Optional[str] = None,
    source_type: Optional[str] = None,
    min_cred: float = 0.0,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    c = _connect()
    sql = "SELECT * FROM evidences WHERE credibility>=?"
    args: List[Any] = [min_cred]
    if brand:
        sql += " AND brand=?"
        args.append(brand)
    if source_type:
        sql += " AND source_type=?"
        args.append(source_type)
    sql += " ORDER BY credibility DESC, captured_at DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in c.execute(sql, args).fetchall()]


def evidence_facets() -> Dict[str, Any]:
    """Aggregate counts by source type and brand."""
    c = _connect()
    total = c.execute("SELECT COUNT(*) n FROM evidences").fetchone()["n"]
    by_type = {
        r["source_type"]: r["n"]
        for r in c.execute(
            "SELECT source_type, COUNT(*) n FROM evidences GROUP BY source_type"
        ).fetchall()
    }
    by_brand = {
        r["brand"]: r["n"]
        for r in c.execute(
            "SELECT brand, COUNT(*) n FROM evidences WHERE brand!='' "
            "GROUP BY brand ORDER BY n DESC LIMIT 12"
        ).fetchall()
    }
    return {"total": total, "by_type": by_type, "by_brand": by_brand}


# ── dashboard ─────────────────────────────────────────────────────────────────
def dashboard_stats() -> Dict[str, Any]:
    c = _connect()
    reports = c.execute("SELECT COUNT(*) n FROM reports").fetchone()["n"]
    ev_total = c.execute("SELECT COUNT(*) n FROM evidences").fetchone()["n"]
    claim_total = c.execute(
        "SELECT COALESCE(SUM(claim_count),0) n FROM reports"
    ).fetchone()["n"]
    high_total = c.execute(
        "SELECT COALESCE(SUM(high_conf_count),0) n FROM reports"
    ).fetchone()["n"]
    avg_ev = round(ev_total / reports, 1) if reports else 0
    fact_rate = round(high_total / claim_total * 100) if claim_total else 0
    facets = evidence_facets()
    intel = intel_overview()
    return {
        "reports": reports,
        "evidence_total": ev_total,
        "claim_total": claim_total,
        "high_conf_total": high_total,
        "avg_evidence_per_report": avg_ev,
        "fact_accuracy": fact_rate,
        "platform_distribution": facets["by_type"],
        "brand_distribution": facets["by_brand"],
        "minutes_saved": intel["minutes_saved"],
        "avg_efficiency": intel["avg_efficiency"],
        "avg_coverage": intel["avg_coverage"],
        "total_tokens": intel["total_tokens"],
        "research_cards": intel["cards"],
    }


def intel_overview() -> Dict[str, Any]:
    """Roll up real per-report metrics across recent research.

    Reads `data.metrics` out of each stored report rather than recomputing, so
    the headline "minutes saved" figure traces back to individual runs.
    """
    c = _connect()
    rows = c.execute(
        "SELECT report_id,title,query,brands,evidence_count,claim_count,"
        "high_conf_count,created_at,data FROM reports ORDER BY created_at DESC LIMIT 60"
    ).fetchall()
    cards: List[Dict[str, Any]] = []
    minutes_saved = 0.0
    eff_list: List[float] = []
    cov_list: List[float] = []
    total_tokens = 0
    for r in rows:
        try:
            data = json.loads(r["data"]) if r["data"] else {}
        except Exception:
            data = {}
        m = data.get("metrics") or {}
        eff = m.get("efficiency") or {}
        cov = m.get("coverage") or {}
        manual_min = float(eff.get("manual_estimate_minutes") or 0)
        elapsed_min = float(eff.get("elapsed_minutes") or 0)
        saved = max(0.0, manual_min - elapsed_min)
        minutes_saved += saved
        if eff.get("efficiency_multiple"):
            eff_list.append(float(eff["efficiency_multiple"]))
        if cov.get("coverage_multiple"):
            cov_list.append(float(cov["coverage_multiple"]))
        total_tokens += int(eff.get("tokens_used") or 0)
        cards.append(
            {
                "id": r["report_id"],
                "title": r["title"],
                "query": r["query"],
                "brands": json.loads(r["brands"] or "[]"),
                "evidence_count": r["evidence_count"],
                "claim_count": r["claim_count"],
                "high_conf_count": r["high_conf_count"],
                "created_at": r["created_at"],
                "efficiency_multiple": eff.get("efficiency_multiple"),
                "coverage_multiple": cov.get("coverage_multiple"),
                "elapsed_minutes": eff.get("elapsed_minutes"),
                "minutes_saved": round(saved, 1),
                "tokens_used": eff.get("tokens_used"),
            }
        )
    return {
        "minutes_saved": round(minutes_saved, 1),
        "avg_efficiency": round(sum(eff_list) / len(eff_list), 1) if eff_list else 0,
        "avg_coverage": round(sum(cov_list) / len(cov_list), 1) if cov_list else 0,
        "total_tokens": total_tokens,
        "cards": cards,
    }


# ── competitor-watch subscriptions ────────────────────────────────────────────
def create_subscription(sub_id: str, query: str, brands: List[str]) -> Dict[str, Any]:
    with _LOCK:
        c = _connect()
        c.execute(
            "INSERT OR REPLACE INTO subscriptions(sub_id,query,brands,created_at,"
            "last_run_at,last_report_id,run_count) VALUES(?,?,?,?,?,?,?)",
            (sub_id, query, json.dumps(brands), _now(), "", "", 0),
        )
        c.commit()
    return get_subscription(sub_id) or {}


def list_subscriptions() -> List[Dict[str, Any]]:
    c = _connect()
    rows = c.execute("SELECT * FROM subscriptions ORDER BY created_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["brands"] = json.loads(d.get("brands") or "[]")
        out.append(d)
    return out


def get_subscription(sub_id: str) -> Optional[Dict[str, Any]]:
    c = _connect()
    row = c.execute("SELECT * FROM subscriptions WHERE sub_id=?", (sub_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["brands"] = json.loads(d.get("brands") or "[]")
    return d


def delete_subscription(sub_id: str) -> None:
    with _LOCK:
        c = _connect()
        c.execute("DELETE FROM subscriptions WHERE sub_id=?", (sub_id,))
        c.commit()


def mark_subscription_run(sub_id: str, report_id: str) -> None:
    with _LOCK:
        c = _connect()
        c.execute(
            "UPDATE subscriptions SET last_run_at=?, last_report_id=?, "
            "run_count=run_count+1 WHERE sub_id=?",
            (_now(), report_id, sub_id),
        )
        c.commit()


# ── expert workload leaderboard ───────────────────────────────────────────────
def bump_expert_stats(
    expert_ids: List[str],
    claims_by_author: Optional[Dict[str, int]] = None,
    evidence_by_collector: Optional[Dict[str, int]] = None,
) -> None:
    claims_by_author = claims_by_author or {}
    evidence_by_collector = evidence_by_collector or {}
    ids = set(expert_ids) | set(claims_by_author) | set(evidence_by_collector)
    with _LOCK:
        c = _connect()
        for eid in ids:
            c.execute(
                "INSERT INTO expert_stats(expert_id,missions,claims_authored,"
                "evidence_collected,last_active) VALUES(?,?,?,?,?)"
                " ON CONFLICT(expert_id) DO UPDATE SET"
                " missions=missions+excluded.missions,"
                " claims_authored=claims_authored+excluded.claims_authored,"
                " evidence_collected=evidence_collected+excluded.evidence_collected,"
                " last_active=excluded.last_active",
                (
                    eid,
                    1 if eid in expert_ids else 0,
                    claims_by_author.get(eid, 0),
                    evidence_by_collector.get(eid, 0),
                    _now(),
                ),
            )
        c.commit()


def expert_workload() -> List[Dict[str, Any]]:
    c = _connect()
    rows = c.execute(
        "SELECT * FROM expert_stats ORDER BY missions DESC, claims_authored DESC"
    ).fetchall()
    return [dict(r) for r in rows]


# ── trace persistence ─────────────────────────────────────────────────────────
def save_traces(task_id: str, report_id: str, spans: List[Dict[str, Any]]) -> None:
    if not spans:
        return
    with _LOCK:
        c = _connect()
        for s in spans:
            c.execute(
                "INSERT OR REPLACE INTO traces(span_id,task_id,report_id,seq,agent_id,stage,"
                "purpose,model,prompt,response,prompt_tokens,completion_tokens,total_tokens,"
                "latency_ms,decision,evidence_ids,ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    s.get("span_id"),
                    task_id,
                    report_id,
                    s.get("seq", 0),
                    s.get("agent_id", ""),
                    s.get("stage", ""),
                    s.get("purpose", ""),
                    s.get("model", ""),
                    (s.get("prompt", "") or "")[:2000],
                    (s.get("response", "") or "")[:2000],
                    s.get("prompt_tokens", 0),
                    s.get("completion_tokens", 0),
                    s.get("total_tokens", 0),
                    s.get("latency_ms", 0),
                    s.get("decision", ""),
                    json.dumps(s.get("evidence_ids", [])),
                    s.get("ts", _now()),
                ),
            )
        c.commit()


def _rows_to_spans(rows) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        d = dict(r)
        d["evidence_ids"] = json.loads(d.get("evidence_ids") or "[]")
        out.append(d)
    return out


def get_traces_by_task(task_id: str) -> List[Dict[str, Any]]:
    c = _connect()
    return _rows_to_spans(
        c.execute("SELECT * FROM traces WHERE task_id=? ORDER BY seq", (task_id,)).fetchall()
    )


def get_traces_by_report(report_id: str) -> List[Dict[str, Any]]:
    c = _connect()
    return _rows_to_spans(
        c.execute(
            "SELECT * FROM traces WHERE report_id=? ORDER BY seq", (report_id,)
        ).fetchall()
    )


# ── reader feedback (human correction rate) ───────────────────────────────────
def save_report_feedback(
    report_id: str, edited_blocks: int, total_blocks: int, data: Dict[str, Any]
) -> None:
    with _LOCK:
        c = _connect()
        c.execute(
            "INSERT OR REPLACE INTO report_feedback(report_id,edited_blocks,total_blocks,"
            "data,updated_at) VALUES(?,?,?,?,?)",
            (report_id, edited_blocks, total_blocks, json.dumps(data), _now()),
        )
        c.commit()


def get_report_feedback(report_id: str) -> Optional[Dict[str, Any]]:
    c = _connect()
    row = c.execute(
        "SELECT * FROM report_feedback WHERE report_id=?", (report_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["data"] = json.loads(d.get("data") or "{}")
    return d
