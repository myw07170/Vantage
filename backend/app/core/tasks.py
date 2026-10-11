"""Explicit background starts and read-only SSE subscriptions."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from app.core import db, trace
from app.core.orchestrator import run_pipeline

class TaskUnavailable(RuntimeError):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code

@dataclass
class Job:
    task_id: str = ""
    events: list[dict] = field(default_factory=list)
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)
    finished: bool = False
    worker: asyncio.Task | None = None

class TaskRunner:
    def __init__(self, pipeline=run_pipeline):
        self.pipeline = pipeline
        self.jobs: dict[str, Job] = {}

    def start(self, task_id: str, payload: dict | None = None) -> dict:
        task = db.get_task(task_id)
        if not task:
            raise TaskUnavailable("Task not found.", 404)
        if task["status"] == "running" and task_id in self.jobs:
            return task
        if not db.claim_task(task_id, payload):
            raise TaskUnavailable("This task has already started or ended. Retry creates a new task.")
        job = Job(task_id=task_id)
        self.jobs[task_id] = job
        job.worker = asyncio.create_task(self._produce(task_id, job))
        return db.get_task(task_id)

    def subscribe(self, task_id: str, after: int = 0):
        task = db.get_task(task_id)
        if not task:
            raise TaskUnavailable("Task not found.", 404)
        job = self.jobs.get(task_id)
        if job:
            return self._events(job, after)
        if task["status"] == "done":
            return self._terminal(task, after, "done", {
                "report_id": task["report_id"], "version_id": task["version_id"],
                "candidate": task["kind"] != "research"})
        if task["status"] in ("failed", "interrupted"):
            return self._terminal(task, after, "error", {"message": task["error"]})
        raise TaskUnavailable("Confirm the scope and start the task before subscribing.")

    async def _terminal(self, task: dict, after: int, kind: str, data: dict):
        seq = max(1, task["terminal_seq"])
        if seq > after:
            yield {"id": seq, "type": kind, "data": data}

    async def _publish(self, job: Job, event: dict):
        if job.task_id:
            task = db.get_task(job.task_id)
            checkpoint = task['checkpoint']
            visual = checkpoint.get('visualization', {'roles': {}, 'activity': [], 'percent': 0, 'rework_rounds': 0})
            kind, data = event['type'], event['data']
            text = ''
            if kind == 'role':
                visual['roles'][data['role']] = data
                visual['percent'] = max(visual['percent'], {'collector': 0, 'analyst': 45, 'reviewer': 70}.get(data['role'], 0))
                text = data['role'].title() + ': ' + data['detail']
            elif kind == 'handoff':
                visual['rework_rounds'] = data['round']
                text = 'Reviewer sent ' + str(len(data['item_ids'])) + ' affected items back for rework ' + str(data['round']) + '/2.'
            elif kind == 'activity':
                text = data['text']
            elif kind == 'notice':
                text = data['message']
            elif kind == 'progress':
                visual['percent'] = max(visual['percent'], data['percent'])
            elif kind == 'error':
                text = data['message']
            elif kind == 'done':
                visual['percent'] = 100
                text = 'Saved result is ready. Unresolved questions remain visible.'
            if kind in ('done', 'error'):
                for state in visual['roles'].values():
                    if state['status'] == 'working':
                        state.update(status='stopped', detail='Execution ended; available work and unresolved issues were retained.')
            if text:
                from app.core.models import now
                visual['activity'] = (visual['activity'] + [{'id': len(job.events)+1, 'kind': kind, 'role': data.get('role',''), 'text': text, 'at': now()}])[-200:]
            db.checkpoint(job.task_id, {**checkpoint, 'visualization': visual})
        async with job.changed:
            job.events.append({**event, "id": len(job.events) + 1})
            job.changed.notify_all()

    async def _produce(self, task_id: str, job: Job):
        status, error = "failed", "Research ended without a result. Retry manually."
        stream = self.pipeline(task_id)
        try:
            async for event in stream:
                if event["type"] == "done":
                    status, error = "done", ""
                    # Persist terminal state before exposing the terminal event.
                    db.finish_task(task_id, status, len(job.events) + 1)
                elif event["type"] == "error":
                    error = event["data"].get("message", error)
                await self._publish(job, event)
                if event["type"] in ("done", "error"):
                    break
            else:
                await self._publish(job, {"type": "error", "data": {"message": error}})
        except asyncio.CancelledError:
            status, error = "interrupted", "Interrupted by backend shutdown. Retry manually."
            await self._publish(job, {"type": "error", "data": {"message": error}})
        except Exception as exc:
            error = str(exc)
            await self._publish(job, {"type": "error", "data": {"message": error}})
        finally:
            await stream.aclose()
            task = db.get_task(task_id)
            db.save_traces(task_id, task.get("report_id") or "", trace.get_trace(task_id))
            db.finish_task(task_id, status, len(job.events), error)
            trace.cleanup(task_id)
            trace.clear_context()
            async with job.changed:
                job.finished = True
                job.changed.notify_all()
            self.jobs.pop(task_id, None)

    async def _events(self, job: Job, after: int):
        index = 0
        while True:
            async with job.changed:
                try:
                    await asyncio.wait_for(job.changed.wait_for(lambda: index < len(job.events) or job.finished), 15)
                except asyncio.TimeoutError:
                    yield_event = {"type": "heartbeat", "data": {}}
                    pending, finished = [yield_event], False
                else:
                    pending = job.events[index:]
                    index = len(job.events)
                    finished = job.finished
            for event in pending:
                if event.get("id", 0) > after or event["type"] == "heartbeat":
                    yield event
            if finished:
                return

    async def close(self):
        workers = [j.worker for j in self.jobs.values() if j.worker]
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        # A task cancelled before its coroutine starts cannot run its finally block.
        for tid, job in list(self.jobs.items()):
            error = "Interrupted by backend shutdown. Retry manually."
            db.finish_task(tid, "interrupted", len(job.events) + 1, error)
            await self._publish(job, {"type": "error", "data": {"message": error}})
            async with job.changed:
                job.finished = True
                job.changed.notify_all()
            self.jobs.pop(tid, None)
