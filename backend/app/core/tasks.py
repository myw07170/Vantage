"""Single-process research jobs, independent of their SSE subscribers.

Only running jobs keep an event buffer. Terminal status and sequence numbers
are durable; reconnecting to a finished job never generates another report.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

from app.core import db, trace
from app.core.orchestrator import run_pipeline


class TaskUnavailable(RuntimeError):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class Job:
    events: list[dict] = field(default_factory=list)
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)
    finished: bool = False
    worker: asyncio.Task | None = None


class TaskRunner:
    def __init__(self, pipeline: Callable = run_pipeline):
        self.pipeline = pipeline
        self.jobs: dict[str, Job] = {}

    def subscribe(self, task_id: str, after: int = 0) -> AsyncIterator[dict]:
        """Reserve synchronously: no await can race two subscribers into a run."""
        task = db.get_task(task_id)
        if not task:
            raise TaskUnavailable("Task not found.", 404)
        job = self.jobs.get(task_id)
        if job is None:
            status = task["status"]
            if status == "done":
                if not task.get("report_id") or not db.get_report(task["report_id"]):
                    raise TaskUnavailable("The task's report was deleted. Create a new task.", 410)
                return self._terminal(task, after, "done", {"reportId": task["report_id"]})
            if status in ("failed", "interrupted"):
                return self._terminal(task, after, "error", {"message": task["error"]})
            if not db.claim_task(task_id):
                raise TaskUnavailable("This task is already running in another backend process.")
            job = Job()
            self.jobs[task_id] = job
            job.worker = asyncio.create_task(self._produce(task_id, job))
        return self._events(job, after)

    async def _terminal(self, task: dict, after: int, kind: str, data: dict):
        seq = max(1, task.get("terminal_seq", 0))
        if seq > after:
            yield {"id": seq, "type": kind, "data": data}

    async def _publish(self, job: Job, event: dict) -> None:
        async with job.changed:
            job.events.append({**event, "id": len(job.events) + 1})
            job.changed.notify_all()

    async def _produce(self, task_id: str, job: Job) -> None:
        status, error = "failed", "Research ended without a report. Create a new task."
        stream = self.pipeline(task_id)
        try:
            async for event in stream:
                await self._publish(job, event)
                if event["type"] == "done":
                    status, error = "done", ""
                    break
                if event["type"] == "error":
                    error = event["data"].get("message", error)
                    break
            else:
                await self._publish(job, {"type": "error", "data": {"message": error}})
        except asyncio.CancelledError:
            status = "interrupted"
            error = "Research was interrupted by backend shutdown. Create a new task."
            await self._publish(job, {"type": "error", "data": {"message": error}})
        except Exception as exc:
            error = str(exc)
            await self._publish(job, {"type": "error", "data": {"message": error}})
        finally:
            await stream.aclose()
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
                await job.changed.wait_for(lambda: index < len(job.events) or job.finished)
                pending = job.events[index:]
                index = len(job.events)
                finished = job.finished
            for event in pending:
                if event["id"] > after:
                    yield event
            if finished:
                return

    async def close(self) -> None:
        workers = [job.worker for job in self.jobs.values() if job.worker]
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        # Cancellation before the coroutine's first step cannot execute its
        # finally block. Persist interruption for those reserved jobs as well.
        for task_id, job in list(self.jobs.items()):
            error = "Research was interrupted by backend shutdown. Create a new task."
            await self._publish(job, {"type": "error", "data": {"message": error}})
            db.finish_task(task_id, "interrupted", len(job.events), error)
            async with job.changed:
                job.finished = True
                job.changed.notify_all()
            self.jobs.pop(task_id, None)
