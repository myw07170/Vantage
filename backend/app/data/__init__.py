"""Loader for the 52-expert roster. Backend and frontend share one experts.json."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

_DATA = Path(__file__).parent / "experts.json"


@lru_cache
def load_experts() -> list[dict]:
    with open(_DATA, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def _index() -> dict[str, dict]:
    """id -> record. Staffing and persona building look experts up in loops,
    so the linear scan this replaces was O(roster) on every prompt built."""
    return {e["id"]: e for e in load_experts()}


def expert_by_id(eid: str) -> Optional[dict]:
    return _index().get(eid)


def experts_by_level(level: str) -> list[dict]:
    return [e for e in load_experts() if e["level"] == level]


def experts_by_group(group: str) -> list[dict]:
    return [e for e in load_experts() if e["group"] == group]
