"""Local single-user comparison API, background tasks and immutable report versions."""
from __future__ import annotations
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import Field
from app.core import db, trace, versions
from app.core.config import get_settings
from app.core.models import Contract, DEFAULT_TOPICS, ResearchScope, all_items
from app.core.tasks import TaskRunner, TaskUnavailable
from app.core.preparation import PreparationRunner, PrepareBody
from app.core import annotations

settings = get_settings()
runner = TaskRunner()
preparer = PreparationRunner()

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.initialize()
    db.interrupt_running_tasks()
    try:
        yield
    finally:
        await preparer.close()
        await runner.close()

app = FastAPI(title="Vantage", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=False)

@app.exception_handler(db.Conflict)
async def conflict_handler(request, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})

@app.exception_handler(TaskUnavailable)
async def task_error_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

@app.exception_handler(KeyError)
async def missing_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc).strip("'")})

@app.exception_handler(ValueError)
async def validation_handler(request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)})

@app.get("/health")
def health():
    return {"status": "ok", "llm_provider": settings.llm_provider, "is_mock": settings.is_mock,
            "llm_configured": settings.llm_configured, "schema_version": db.SCHEMA_VERSION}

@app.get("/api/settings")
def public_settings():
    return {"default_topics": DEFAULT_TOPICS, "token_limit": settings.research_token_limit,
            "time_limit_seconds": settings.research_time_limit_seconds,
            "llm_provider": settings.llm_provider, "is_mock": settings.is_mock}

class CreateTaskBody(Contract):
    query: str = Field(min_length=1, max_length=4000)

@app.post("/api/tasks", status_code=201)
def create_task(body: CreateTaskBody):
    # Draft creation is local; no model or search calls before scope confirmation.
    return db.save_task(body.query)

@app.get("/api/tasks")
def tasks():
    return db.list_tasks()

@app.post("/api/tasks/{task_id}/prepare", status_code=202)
async def prepare_task(task_id: str, body: PrepareBody):
    if not settings.llm_configured:
        raise HTTPException(503, settings.llm_configuration_error)
    return preparer.start(task_id, body)

@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    task = db.get_task(task_id)
    if not task:
        raise KeyError("Task not found.")
    return task

@app.post("/api/tasks/{task_id}/start")
async def start_task(task_id: str, scope: ResearchScope):
    task = get_task(task_id)
    if task["kind"] != "research":
        raise ValueError("Follow-up and review tasks already have a fixed scope.")
    if not settings.llm_configured:
        raise HTTPException(503, settings.llm_configuration_error)
    return runner.start(task_id, {**task['payload'], "scope": scope.model_dump()})

@app.post("/api/tasks/{task_id}/retry", status_code=201)
async def retry_task(task_id: str):
    task = get_task(task_id)
    if task["status"] not in ("failed", "interrupted"):
        raise db.Conflict("Only failed or interrupted tasks can be retried.")
    if not settings.llm_configured:
        raise HTTPException(503, settings.llm_configuration_error)
    # New task ID and independent budget, with the original checkpoint retained.
    new = db.save_task(task["query"], task["kind"], {**task["payload"], "retry_of": task_id}, task["report_id"])
    return runner.start(new["task_id"])

@app.get("/api/tasks/{task_id}/stream")
async def stream_task(task_id: str, request: Request, after: int = Query(0, ge=0)):
    try:
        cursor = max(after, int(request.headers.get("Last-Event-ID", "0")))
    except ValueError:
        raise HTTPException(400, "Invalid Last-Event-ID.")
    events = runner.subscribe(task_id, cursor)
    async def generate():
        async for event in events:
            if await request.is_disconnected():
                break
            if event["type"] == "heartbeat":
                yield ": heartbeat\n\n"
            else:
                yield f'id: {event["id"]}\nevent: {event["type"]}\ndata: {json.dumps(event["data"])}\n\n'
    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/api/tasks/{task_id}/trace")
def task_trace(task_id: str):
    get_task(task_id)
    return {"spans": trace.get_trace(task_id) or db.get_traces_by_task(task_id)}

@app.get("/api/reports")
def reports():
    return db.list_reports()

@app.get("/api/reports/{report_id}")
def get_report(report_id: str):
    report = db.get_report(report_id)
    if not report:
        raise KeyError("Report not found.")
    return report

@app.get("/api/reports/{report_id}/versions")
def report_versions(report_id: str):
    get_report(report_id)
    return db.list_versions(report_id)

@app.get("/api/reports/{report_id}/versions/{version_id}")
def report_version(report_id: str, version_id: str):
    return versions.require_version(report_id, version_id)

@app.get("/api/reports/{report_id}/trace")
def report_trace(report_id: str):
    get_report(report_id)
    return {"spans": db.get_traces_by_report(report_id)}

class ReportPatch(Contract):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    starred: bool | None = None

@app.patch("/api/reports/{report_id}")
def patch_report(report_id: str, body: ReportPatch):
    get_report(report_id)
    return db.update_report(report_id, body.title, body.starred)

@app.delete("/api/reports/{report_id}")
def delete_report(report_id: str):
    if not db.delete_report(report_id):
        raise KeyError("Report not found.")
    return {"ok": True}

class FollowupBody(Contract):
    base_version_id: str
    target_ids: list[str] = Field(min_length=1)
    selected_text: str = Field(default="", max_length=20000)
    question: str = Field(min_length=1, max_length=4000)

class ReviewBody(Contract):
    base_version_id: str
    target_ids: list[str] = Field(default_factory=list)

def task_from_version(report_id: str, base_version_id: str, target_ids: list[str], kind: str, **extra):
    get_report(report_id)
    base = versions.require_version(report_id, base_version_id)
    if base["state"] != "applied":
        raise ValueError("Start follow-up work from an applied report version.")
    content = base["content"]
    items = {i["id"]: i for i in all_items(content)}
    if any(t not in items for t in target_ids):
        raise ValueError("A target item is not present in the base version.")
    selected = extra.get("selected_text", "")
    if selected and not any(selected in items[t]["text"] for t in target_ids):
        raise ValueError("The selected text is not in the targeted base-version content.")
    if not settings.llm_configured:
        raise HTTPException(503, settings.llm_configuration_error)
    scope = ResearchScope(products=content["products"], topics=content["topics"], scope_acknowledged=True,
                          limitations="Follow-up is limited to the selected content and original confirmed scope.")
    task = db.save_task(extra.get("question", "Review selected report content"), kind,
                        {"scope": scope.model_dump(), "base_version_id": base_version_id,
                         "target_ids": target_ids, **extra}, report_id)
    return runner.start(task["task_id"])

@app.post("/api/reports/{report_id}/followups", status_code=202)
async def followup(report_id: str, body: FollowupBody):
    return task_from_version(report_id, body.base_version_id, body.target_ids, "followup",
                             question=body.question, selected_text=body.selected_text)

@app.post("/api/reports/{report_id}/reviews", status_code=202)
async def review_report(report_id: str, body: ReviewBody):
    return task_from_version(report_id, body.base_version_id, body.target_ids, "review")

class EditBody(Contract):
    base_version_id: str
    edits: dict[str, str]

class ApplyBody(Contract):
    base_version_id: str
    candidate_version_id: str

class RestoreBody(Contract):
    base_version_id: str
    version_id: str

@app.post("/api/reports/{report_id}/edits", status_code=201)
def edit_report(report_id: str, body: EditBody):
    return versions.edit(report_id, body.base_version_id, body.edits)

@app.post("/api/reports/{report_id}/apply", status_code=201)
def apply_candidate(report_id: str, body: ApplyBody):
    return versions.apply(report_id, body.base_version_id, body.candidate_version_id)

@app.post("/api/reports/{report_id}/restore", status_code=201)
def restore_version(report_id: str, body: RestoreBody):
    return versions.restore(report_id, body.base_version_id, body.version_id)

@app.get("/api/reports/{report_id}/annotations")
def report_annotations(report_id: str, version_id: str):
    return annotations.list_annotations(report_id, version_id)

@app.post("/api/reports/{report_id}/annotations", status_code=201)
def add_annotation(report_id: str, body: annotations.AnnotationBody):
    return annotations.create(report_id, body)

@app.patch("/api/reports/{report_id}/annotations/{annotation_id}")
def update_annotation(report_id: str, annotation_id: str, body: annotations.AnnotationPatch):
    return annotations.mutate(report_id, annotation_id, body.version_id, body.revision, body.model_dump())

@app.delete("/api/reports/{report_id}/annotations/{annotation_id}")
def delete_annotation(report_id: str, annotation_id: str, version_id: str, revision: int = Query(ge=1)):
    return annotations.mutate(report_id, annotation_id, version_id, revision)
