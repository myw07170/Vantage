"""Per-task budgets shared safely with blocking workers through ContextVar."""
from __future__ import annotations
import contextvars
import threading
import time

class BudgetExceeded(RuntimeError):
    pass

class Budget:
    def __init__(self, tokens: int, seconds: float):
        self.limit = tokens
        self.deadline = time.monotonic() + seconds
        self.started = time.monotonic()
        self.used = 0
        self.estimated = False
        self.cancelled = threading.Event()
        self.lock = threading.Lock()

    def check(self) -> float:
        remaining = self.deadline - time.monotonic()
        if self.cancelled.is_set() or remaining <= 0:
            raise BudgetExceeded("Task time limit reached or task interrupted.")
        if self.used >= self.limit:
            raise BudgetExceeded("Task token limit reached.")
        return remaining

    def reserve(self, tokens: int) -> None:
        with self.lock:
            self.check()
            if self.used + tokens > self.limit:
                raise BudgetExceeded("Insufficient remaining tokens for the next model call.")
            self.used += tokens

    def reconcile(self, reserved: int, actual: int | None) -> None:
        with self.lock:
            if actual is None:
                self.estimated = True
            else:
                self.used += max(0, actual) - reserved

    def sleep(self, seconds: float) -> None:
        remaining = self.check()
        if seconds >= remaining:
            raise BudgetExceeded("Task time limit prevents another retry.")
        if self.cancelled.wait(seconds):
            raise BudgetExceeded("Task interrupted.")
        self.check()

    def snapshot(self) -> dict:
        return {"tokens": self.used, "token_limit": self.limit, "usage_estimated": self.estimated,
                "elapsed_seconds": round(time.monotonic() - self.started, 2),
                "remaining_seconds": max(0, round(self.deadline - time.monotonic(), 2))}

CURRENT: contextvars.ContextVar[Budget | None] = contextvars.ContextVar("research_budget", default=None)

def check() -> None:
    budget = CURRENT.get()
    if budget:
        budget.check()
