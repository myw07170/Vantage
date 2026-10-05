"""Vantage API (FastAPI).

Exposes the expert roster, task creation and clarification, the SSE research
stream, reports and history, the dashboard, the global evidence library,
competitor-watch subscriptions, the expert workload board, and health checks.

Configurable LLM providers, live web collection and SQLite persistence.
Mock replaces model inference only; collection still uses real providers.
"""
from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core import db
from app.core import search as search_mod
from app.core.config import get_settings
from app.core.llm import LLMNotConfigured, chat, quota_snapshot
from app.core.orchestrator import (
    create_task,
    refine_section,
    submit_clarify,
)
from app.data import expert_by_id, load_experts
from app.core.tasks import TaskRunner, TaskUnavailable

settings = get_settings()

runner = TaskRunner()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.interrupt_running_tasks()
    try:
        yield
    finally:
        await runner.close()


app = FastAPI(title="Vantage API", version="1.0.0", lifespan=lifespan)

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
        "llm_provider": settings.llm_provider,
        "is_mock": settings.is_mock,
        "experts": len(load_experts()),
    }


@app.get("/health")
def health():
    return {"status": "ok", "llm_configured": settings.llm_configured,
            "llm_provider": settings.llm_provider, "is_mock": settings.is_mock}


@app.get("/api/llm/ping")
def llm_ping():
    """Check the selected provider and show locally configured quota usage."""
    try:
        reply = chat(
            [
                {"role": "system", "content": "Reply with a single word."},
                {"role": "user", "content": "Say: ready"},
            ],
            max_tokens=200,
            task_kind="echo",
            mock_context={"text": "ready"},
        )
        return {
            "ok": True,
            "model": settings.llm_model_core,
            "fast_model": settings.llm_model_fast,
            "llm_provider": settings.llm_provider,
            "is_mock": settings.is_mock,
            "reply": reply.strip(),
            "quota": quota_snapshot(),
        }
    except LLMNotConfigured as e:
        return {"ok": False, "reason": "not_configured", "message": str(e),
                "llm_provider": settings.llm_provider, "is_mock": settings.is_mock}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": "error", "message": str(e),
                "llm_provider": settings.llm_provider, "is_mock": settings.is_mock}


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
        raise HTTPException(404, "Expert not found.")
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
    query: str = Field(min_length=1, max_length=4000)
    mode: Literal["quick", "deep", "expert"] = "deep"
    subscription_id: str = ""

    @field_validator("query")
    @classmethod
    def non_blank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Query cannot be blank.")
        return value.strip()


@app.post("/api/tasks")
def post_task(body: CreateTaskBody):
    if body.subscription_id and not db.get_subscription(body.subscription_id):
        raise HTTPException(404, "Subscription not found.")
    try:
        return create_task(body.query, mode=body.mode, subscription_id=body.subscription_id)
    except LLMNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found.")
    clar = task["clarifications"]
    return {"taskId": task_id, "query": task["query"], "mode": clar.get("_mode", "deep"),
            "status": task["status"], "reportId": task.get("report_id"),
            "error": task["error"], "terminalSeq": task["terminal_seq"],
            "clarifyQuestions": clar.get("_questions", []),
            "answers": {k: v for k, v in clar.items() if not k.startswith("_")}}


class ClarifyBody(BaseModel):
    answers: dict = Field(default_factory=dict)


@app.post("/api/tasks/{task_id}/clarify")
def post_clarify(task_id: str, body: ClarifyBody):
    if not db.get_task(task_id):
        raise HTTPException(404, "Task not found.")
    result = submit_clarify(task_id, body.answers)
    if not result["ok"]:
        raise HTTPException(409, result["message"])
    return result


# ── SSE research stream ───────────────────────────────────────────────────────
@app.get("/api/tasks/{task_id}/stream")
async def stream_task(task_id: str, request: Request, after: int = Query(0, ge=0)):
    """Start a task once; every connection subscribes to the same job."""
    try:
        header_cursor = int(request.headers.get("Last-Event-ID", "0"))
        if header_cursor < 0:
            raise ValueError("negative cursor")
        cursor = max(after, header_cursor)
    except ValueError as exc:
        raise HTTPException(422, "Invalid event cursor.") from exc
    try:
        events = runner.subscribe(task_id, cursor)
    except TaskUnavailable as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc

    async def gen():
        try:
            async for ev in events:
                if await request.is_disconnected():
                    break
                etype = ev["type"]
                data = json.dumps(ev["data"])
                yield f"id: {ev['id']}\nevent: {etype}\ndata: {data}\n\n"
        finally:
            await events.aclose()

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
        raise HTTPException(404, "Report not found.")
    return rep


class ReportPatch(BaseModel):
    """Both fields optional: the sidebar sends one or the other, never both."""

    title: Optional[str] = None
    starred: Optional[bool] = None


@app.patch("/api/reports/{report_id}")
def patch_report(report_id: str, body: ReportPatch):
    """Renames or stars a report. Presentation only — the analysis is untouched."""
    card = db.update_report(report_id, title=body.title, starred=body.starred)
    if card is None:
        raise HTTPException(404, "Report not found.")
    return {"ok": True, "report": card}


@app.delete("/api/reports/{report_id}")
def delete_report(report_id: str):
    """Deletes the report along with its evidence, traces and feedback."""
    if not db.delete_report(report_id):
        raise HTTPException(404, "Report not found.")
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
    edited_blocks: int = Field(0, ge=0)
    total_blocks: int = Field(0, ge=0)
    data: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_counts(self):
        if self.edited_blocks > self.total_blocks:
            raise ValueError("Edited blocks cannot exceed total blocks.")
        return self


@app.post("/api/reports/{report_id}/feedback")
def post_feedback(report_id: str, body: FeedbackBody):
    rep = db.get_report(report_id)
    if not rep:
        raise HTTPException(404, "Report not found.")
    db.save_report_feedback(
        report_id, body.edited_blocks, body.total_blocks, body.data
    )
    if rep and rep.get("metrics"):
        from app.core.metrics import apply_feedback

        rep["metrics"] = apply_feedback(
            rep["metrics"], body.edited_blocks, body.total_blocks
        )
        db.save_report(rep, task_id="")
    return {"ok": True, "report": rep}


# ── Annotation-driven section refinement ──────────────────────────────────────
class RefineBody(BaseModel):
    section_id: str
    annotations: List[str] = Field(default_factory=list)


@app.post("/api/reports/{report_id}/refine")
def post_refine(report_id: str, body: RefineBody):
    rep = db.get_report(report_id)
    if not rep or not any(s["id"] == body.section_id for s in rep["sections"]):
        raise HTTPException(404, "Report or section not found.")
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
class SubscriptionBody(CreateTaskBody):
    brands: List[str] = Field(default_factory=list)


@app.get("/api/subscriptions")
def list_subscriptions():
    return db.list_subscriptions()


@app.post("/api/subscriptions")
def create_subscription(body: SubscriptionBody):
    sub_id = f"sub_{uuid.uuid4().hex[:8]}"
    return db.create_subscription(sub_id, body.query, body.brands)


@app.delete("/api/subscriptions/{sub_id}")
def delete_subscription(sub_id: str):
    if not db.delete_subscription(sub_id):
        raise HTTPException(404, "Subscription not found.")
    return {"ok": True}
