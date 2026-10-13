"""Observability trace: every agent's prompt, output, tokens and decision.

Design note — zero-intrusion instrumentation
--------------------------------------------
The pipeline wraps all blocking work in `asyncio.to_thread`, which does
`copy_context()` and runs the function via `ctx.run(...)` inside the worker
thread. So a contextvar set on the async side before the hop is visible to the
nested synchronous `llm.chat()` running in that thread. That is how a span
learns which agent and stage it belongs to without any call site passing it.

Flow: `chat()` records a span automatically → the pipeline calls `drain()` at
each stage boundary and pushes the new spans over SSE → a trimmed copy is
persisted with the report for the "decision replay" view.

Buffers are in-memory, so this is single-process by design.
"""
from __future__ import annotations

import contextvars
import datetime as _dt
import itertools
import threading
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# Label used for spans that record a non-LLM step (search, rule-based checks).
NO_LLM = "— (retrieval / rules, no LLM)"


@dataclass
class TraceSpan:
    span_id: str
    task_id: str
    seq: int
    agent_id: str
    stage: str
    purpose: str
    model: str
    prompt: str          # trimmed summary of system + user messages
    response: str        # trimmed
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int
    decision: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    ts: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Current call context: task_id, agent_id, stage, purpose.
_CTX: contextvars.ContextVar[Dict[str, str]] = contextvars.ContextVar(
    "vantage_trace_ctx", default={}
)

_BUFFER: Dict[str, List[TraceSpan]] = {}
_DRAINED: Dict[str, int] = {}          # task_id -> index already drained
_LOCK = threading.Lock()
_SEQ = itertools.count(1)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def set_context(task_id: str, agent_id: str, stage: str, purpose: str) -> None:
    """Set before hopping to a thread; `chat()` in that thread reads it."""
    _CTX.set(
        {"task_id": task_id, "agent_id": agent_id, "stage": stage, "purpose": purpose}
    )


def clear_context() -> None:
    _CTX.set({})


def _summarize_messages(messages: Any, limit: int = 600) -> str:
    try:
        parts = []
        for m in messages:
            role = m.get("role", "")
            content = str(m.get("content", ""))
            parts.append(f"[{role}] {content}")
        text = "\n".join(parts)
    except Exception:
        text = str(messages)
    return text[:limit]


def record_span(
    model: str,
    messages: Any,
    response: str,
    usage: Any = None,
    latency_ms: int = 0,
    decision: str = "",
    evidence_ids: Optional[List[str]] = None,
) -> Optional[TraceSpan]:
    """Called by `llm.chat()` after every call.

    `usage` is any object exposing `prompt_tokens` / `completion_tokens` /
    `total_tokens`; llm.py normalizes the provider's own shape into that.
    """
    ctx = _CTX.get()
    task_id = ctx.get("task_id", "")
    if not task_id:
        return None  # outside a research run (e.g. a health-check ping)

    pt = ct = tt = 0
    try:
        if usage is not None:
            pt = int(getattr(usage, "prompt_tokens", 0) or 0)
            ct = int(getattr(usage, "completion_tokens", 0) or 0)
            tt = int(getattr(usage, "total_tokens", 0) or 0)
    except Exception:
        pass

    span = TraceSpan(
        span_id="sp_" + uuid.uuid4().hex[:10],
        task_id=task_id,
        seq=next(_SEQ),
        agent_id=ctx.get("agent_id", ""),
        stage=ctx.get("stage", ""),
        purpose=ctx.get("purpose", ""),
        model=model,
        prompt=_summarize_messages(messages),
        response=str(response or "")[:600],
        prompt_tokens=pt,
        completion_tokens=ct,
        total_tokens=tt,
        latency_ms=int(latency_ms),
        decision=decision,
        evidence_ids=list(evidence_ids or []),
        ts=_now(),
    )
    with _LOCK:
        _BUFFER.setdefault(task_id, []).append(span)
    return span


def record_manual_span(
    task_id: str,
    agent_id: str,
    stage: str,
    purpose: str,
    detail: str = "",
    decision: str = "",
    evidence_ids: Optional[List[str]] = None,
    latency_ms: int = 0,
    model: str = NO_LLM,
) -> Optional[TraceSpan]:
    """Record a non-LLM step (evidence collection, rule-based quality checks).

    Without this, stages that never call a model would appear blank in the
    decision replay. `detail` is shown as that step's input/output summary.
    """
    if not task_id:
        return None
    span = TraceSpan(
        span_id="sp_" + uuid.uuid4().hex[:10],
        task_id=task_id,
        seq=next(_SEQ),
        agent_id=agent_id,
        stage=stage,
        purpose=purpose,
        model=model,
        prompt=str(detail or "")[:600],
        response=str(decision or detail or "")[:600],
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        latency_ms=int(latency_ms),
        decision=decision,
        evidence_ids=list(evidence_ids or []),
        ts=_now(),
    )
    with _LOCK:
        _BUFFER.setdefault(task_id, []).append(span)
    return span


def drain(task_id: str) -> List[Dict[str, Any]]:
    """Spans added since the last drain, for incremental SSE push."""
    with _LOCK:
        spans = _BUFFER.get(task_id, [])
        start = _DRAINED.get(task_id, 0)
        new = spans[start:]
        _DRAINED[task_id] = len(spans)
        return [s.to_dict() for s in new]


def get_trace(task_id: str) -> List[Dict[str, Any]]:
    """All spans for a task (used while it is still running)."""
    with _LOCK:
        return [s.to_dict() for s in _BUFFER.get(task_id, [])]


def cleanup(task_id: str) -> None:
    """Drop the in-memory buffer once the task is persisted."""
    with _LOCK:
        _BUFFER.pop(task_id, None)
        _DRAINED.pop(task_id, None)
