"""Vantage API (FastAPI).

Exposes the expert roster, task creation and clarification, the SSE research
stream, reports and history, the dashboard, the global evidence library,
competitor-watch subscriptions, the expert workload board, and health checks.

Real Gemini calls, real web search, real page fetching, real SQLite. No demo
mode and no synthetic data.
"""
from __future__ import annotations

import json
import uuid
from typing import List, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core import db
from app.core import search as search_mod
from app.core.config import get_settings
from app.core.llm import LLMNotConfigured, chat, quota_snapshot
from app.core.orchestrator import (
    create_task,
    refine_section,
    run_pipeline,
    submit_clarify,
)
from app.data import expert_by_id, load_experts

settings = get_settings()

app = FastAPI(title="Vantage API", version="1.0.0")

# Scoped to the configured frontend origin rather than "*" — the API has no
# authentication, so there is no reason to let any site call it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "name": "Vantage API",
        "version": "1.0.0",
        "slogan": "Every conclusion carries its source.",
        "llm_configured": settings.llm_configured,
        "experts": len(load_experts()),
    }


@app.get("/health")
def health():
    return {"status": "ok", "llm_configured": settings.llm_configured}


@app.get("/api/llm/ping")
def llm_ping():
    """Live model check, plus how much of today's free-tier quota is left."""
    try:
        reply = chat(
            [
                {"role": "system", "content": "Reply with a single word."},
                {"role": "user", "content": "Say: ready"},
            ],
            max_tokens=200,
        )
        return {
            "ok": True,
            "model": settings.gemini_model_core,
            "fast_model": settings.gemini_model_fast,
            "reply": reply.strip(),
            "quota": quota_snapshot(),
        }
    except LLMNotConfigured as e:
        return {"ok": False, "reason": "not_configured", "message": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": "error", "message": str(e)}


@app.get("/api/search")
def search_endpoint(q: str, num: int = 10, site: Optional[str] = None):
    """Raw search passthrough, for debugging the provider chain."""
    try:
        results = search_mod.search(q, num=num, site=site)
        return {
            "ok": True, "query": q, "site": site, "results": results,
            "providers": search_mod.provider_status(),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False, "query": q, "reason": "error", "message": str(e),
            "providers": search_mod.provider_status(),
        }


# ── Experts ───────────────────────────────────────────────────────────────────
@app.get("/api/experts")
def list_experts():
    return load_experts()


@app.get("/api/experts/workload")
def experts_workload():
    """Leaderboard of real accumulated missions, claims and evidence."""
    stats = {s["expert_id"]: s for s in db.expert_workload()}
    out = []
    for e in load_experts():
        s = stats.get(e["id"])
        out.append(
            {
                "id": e["id"],
                "name": e.get("name", e["id"]),
                "title": e.get("role_title", ""),
                "layer": e.get("level", ""),
                "avatar": e.get("avatar", ""),
                "missions": s["missions"] if s else 0,
                "claims_authored": s["claims_authored"] if s else 0,
                "evidence_collected": s["evidence_collected"] if s else 0,
                "last_active": s["last_active"] if s else "",
            }
        )
    out.sort(
        key=lambda x: (x["missions"], x["claims_authored"], x["evidence_collected"]),
        reverse=True,
    )
    return out


@app.get("/api/experts/{eid}")
def get_expert(eid: str):
    e = expert_by_id(eid)
    if not e:
        return {"ok": False, "message": "not found"}
    stat = next((s for s in db.expert_workload() if s["expert_id"] == eid), None)
    return {
        **e,
        "stats": stat
        or {
            "missions": 0, "claims_authored": 0,
            "evidence_collected": 0, "last_active": "",
        },
    }


# ── Tasks and clarification ───────────────────────────────────────────────────
class CreateTaskBody(BaseModel):
    query: str
    mode: str = "deep"  # quick | deep | expert


@app.post("/api/tasks")
def post_task(body: CreateTaskBody):
    return create_task(body.query, mode=body.mode)


class ClarifyBody(BaseModel):
    answers: dict = {}


@app.post("/api/tasks/{task_id}/clarify")
def post_clarify(task_id: str, body: ClarifyBody):
    return submit_clarify(task_id, body.answers)


# ── SSE research stream ───────────────────────────────────────────────────────
@app.get("/api/tasks/{task_id}/stream")
async def stream_task(task_id: str, request: Request, sub_id: str = ""):
    """Runs the whole pipeline, streaming events as they happen.

    Note this GET *starts* the research — it is not idempotent, and a reconnect
    re-runs it. Each event carries a monotonic `id:` so the client can drop
    duplicates if the browser auto-reconnects mid-run.
    """

    async def gen():
        seq = 0
        try:
            async for ev in run_pipeline(task_id, sub_id=sub_id):
                if await request.is_disconnected():
                    break
                seq += 1
                etype = ev["type"]
                data = json.dumps(ev["data"])
                yield f"id: {seq}\nevent: {etype}\ndata: {data}\n\n"
        except Exception as e:  # noqa: BLE001
            err = json.dumps({"message": str(e)})
            yield f"event: error\ndata: {err}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Reports and history ───────────────────────────────────────────────────────
@app.get("/api/reports")
def list_reports():
    return db.list_reports()


@app.get("/api/reports/{report_id}")
def get_report(report_id: str):
    rep = db.get_report(report_id)
    if not rep:
        return {"ok": False, "message": "report not ready"}
    return rep


@app.delete("/api/reports/{report_id}")
def delete_report(report_id: str):
    """Deletes the report along with its evidence, traces and feedback."""
    if not db.delete_report(report_id):
        return {"ok": False, "message": "report not found"}
    return {"ok": True}


# ── Observability traces ──────────────────────────────────────────────────────
@app.get("/api/tasks/{task_id}/trace")
def get_task_trace(task_id: str):
    from app.core import trace as _trace

    spans = _trace.get_trace(task_id) or db.get_traces_by_task(task_id)
    return {"taskId": task_id, "spans": spans}


@app.get("/api/reports/{report_id}/trace")
def get_report_trace(report_id: str):
    spans = db.get_traces_by_report(report_id)
    if not spans:
        rep = db.get_report(report_id)
        spans = (rep or {}).get("trace", [])
    return {"reportId": report_id, "spans": spans}


# ── Reader feedback -> human correction rate ──────────────────────────────────
class FeedbackBody(BaseModel):
    edited_blocks: int = 0
    total_blocks: int = 0
    data: dict = {}


@app.post("/api/reports/{report_id}/feedback")
def post_feedback(report_id: str, body: FeedbackBody):
    db.save_report_feedback(
        report_id, body.edited_blocks, body.total_blocks, body.data
    )
    rep = db.get_report(report_id)
    if rep and rep.get("metrics"):
        from app.core.metrics import apply_feedback

        rep["metrics"] = apply_feedback(
            rep["metrics"], body.edited_blocks, body.total_blocks
        )
        db.save_report(rep, task_id="")
    return {"ok": True}


# ── Annotation-driven section refinement ──────────────────────────────────────
class RefineBody(BaseModel):
    section_id: str
    annotations: List[str] = []


@app.post("/api/reports/{report_id}/refine")
def post_refine(report_id: str, body: RefineBody):
    return refine_section(report_id, body.section_id, body.annotations)


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.get("/api/dashboard")
def dashboard():
    return db.dashboard_stats()


# ── Global evidence library ───────────────────────────────────────────────────
@app.get("/api/evidences")
def evidences(
    brand: Optional[str] = None,
    source_type: Optional[str] = None,
    min_cred: float = 0.0,
    limit: int = 200,
):
    items = db.query_evidences(
        brand=brand, source_type=source_type, min_cred=min_cred, limit=limit
    )
    return {"items": items, "facets": db.evidence_facets()}


# ── Competitor-watch subscriptions ────────────────────────────────────────────
class SubscriptionBody(BaseModel):
    query: str
    brands: List[str] = []


@app.get("/api/subscriptions")
def list_subscriptions():
    return db.list_subscriptions()


@app.post("/api/subscriptions")
def create_subscription(body: SubscriptionBody):
    sub_id = f"sub_{uuid.uuid4().hex[:8]}"
    return db.create_subscription(sub_id, body.query, body.brands)


@app.delete("/api/subscriptions/{sub_id}")
def delete_subscription(sub_id: str):
    db.delete_subscription(sub_id)
    return {"ok": True}
