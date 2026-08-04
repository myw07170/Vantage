"""Roster as a behavior layer: prompt personas, staffing and stage routing.

The profiles in `experts.json` carry real sourcing grounding — an analyst's
`knowledge_base` names the databases they actually work from, and their
`knowledge_tags` name the terms a brief on their subject would use. This module
is what makes that grounding do work: `persona_block` and `team_block` build the
system-prompt preamble, `score_roster` / `shortlist` / `normalize_team` decide
who is staffed, and `assign_stages` / `section_writer` decide which stage and
which section each of them owns.

Staffing is deterministic here and only the final pick is left to a model.
Lexical scoring against tags is crude, but it is repeatable, costs no tokens,
and keeps the beauty analyst off a cloud-infrastructure brief before the
dispatch call ever sees the roster.

The three L3 leads are permanent staff rather than model picks. The pipeline
has always routed intake to the director, audit to the quality officer and
authorship to the chief analyst regardless of what dispatch returned; making
that structural rather than incidental removes a contradiction and leaves the
dispatch call a smaller, better-defined job.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Sequence

from app.data import expert_by_id, experts_by_group, experts_by_level, load_experts

# ── The permanent decision tier ───────────────────────────────────────────────
DIRECTOR = "L3-001"        # scopes the brief, assembles the team, signs off
CHIEF_ANALYST = "L3-002"   # owns analytical rigor and authorship
QUALITY = "L3-003"         # red-teams the work, drives rework

PERMANENT_L3: tuple[str, ...] = (DIRECTOR, CHIEF_ANALYST, QUALITY)

_L3_REASONS = {
    DIRECTOR: "Directs the engagement, scopes the brief and signs off",
    CHIEF_ANALYST: "Owns analytical rigor and authors the report",
    QUALITY: "Red-teams the work and enforces the four iron rules",
}

# Team size bounds. The dispatch prompt asks for these; `normalize_team`
# enforces them, because a model that returns eight L1s and no strategy advisor
# would otherwise degrade the run silently.
MIN_L2, MAX_L2 = 1, 2
MIN_L1, MAX_L1 = 3, 6


# ── Prompt blocks ─────────────────────────────────────────────────────────────
# A persona sets voice and sourcing instinct. It must never be read as licence
# to supply domain facts from memory — this product's whole claim is that every
# conclusion carries its source, so the guard is attached to every block.
GROUNDING_GUARD = (
    "Your background shapes which sources you reach for and what you "
    "interrogate. It never licenses a claim the evidence below does not "
    "support."
)

_KB_MAX_WORDS = 60
_TEAM_MAX_MEMBERS = 12
_TEAM_MAX_TAGS = 6


def _truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(",;:.") + "…"


def persona_block(eid: str) -> str:
    """System-prompt preamble putting one expert in the chair.

    Returns "" for an unknown id so every call site degrades to the generic
    analyst voice rather than failing.
    """
    e = expert_by_id(eid)
    if not e:
        return ""
    lines = [
        f"You are {e['name']} (\"{e['nickname']}\"), {e['role_title']}, "
        "on this engagement."
    ]
    if e.get("one_liner"):
        lines.append(e["one_liner"])
    if e.get("knowledge_base"):
        lines.append("How you work: " + _truncate_words(e["knowledge_base"], _KB_MAX_WORDS))
    if e.get("knowledge_tags"):
        lines.append("You reach for: " + ", ".join(e["knowledge_tags"]))
    lines.append(GROUNDING_GUARD)
    return "\n".join(lines) + "\n\n"


def team_block(member_ids: Sequence[str], limit: int = _TEAM_MAX_MEMBERS) -> str:
    """Preamble for prompts the whole team contributes to.

    One line per member rather than full profiles: the analysis prompts need to
    know which specialisms are in the room, not each analyst's biography.
    """
    rows = []
    for eid in list(member_ids)[:limit]:
        e = expert_by_id(eid)
        if not e:
            continue
        row = f"- {e['name']}, {e['role_title']}"
        tags = e.get("knowledge_tags", [])[:_TEAM_MAX_TAGS]
        if tags:
            row += f" — works from {', '.join(tags)}"
        rows.append(row)
    if not rows:
        return ""
    return (
        "You are the analysis team staffed on this engagement:\n"
        + "\n".join(rows)
        + "\n"
        + GROUNDING_GUARD
        + "\n\n"
    )


# ── Lexical scoring ───────────────────────────────────────────────────────────
_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Words that appear in almost every brief and would match almost every profile.
_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "over", "than",
    "versus", "compare", "comparison", "competitive", "competitor", "competitors",
    "analysis", "analyst", "market", "product", "products", "company", "companies",
    "business", "research", "report", "data", "best", "top", "how", "what", "why",
    "who", "which", "does", "are", "its", "their", "our", "new", "use", "using",
}


def _tokens(text: str) -> set[str]:
    return {
        t for t in _TOKEN_RE.findall((text or "").lower())
        if len(t) > 2 and t not in _STOPWORDS
    }


_W_TAG, _W_SKILL, _W_ROLE, _W_KB = 3, 2, 2, 1
# The knowledge_base runs ~60 words against 4-8 tags, so uncapped it would
# drown the signal that actually matters. Tags are the deliberate index.
_KB_HIT_CAP = 4


def score_expert(e: Dict, brief: set[str]) -> int:
    """How well one profile matches a tokenized brief."""
    if not brief:
        return 0
    score = 0
    for tag in e.get("knowledge_tags", []):
        if _tokens(tag) & brief:
            score += _W_TAG
    for skill in e.get("skills", []):
        if _tokens(skill) & brief:
            score += _W_SKILL
    if _tokens(e.get("role_title", "")) & brief:
        score += _W_ROLE
    kb_hits = len(_tokens(e.get("knowledge_base", "")) & brief)
    score += min(kb_hits, _KB_HIT_CAP) * _W_KB
    return score


def score_roster(query: str, brands: Sequence[str], focus: Sequence[str]) -> Dict[str, int]:
    """Score every expert against the brief. Keyed by expert id."""
    brief = _tokens(" ".join([query, *brands, *focus]))
    return {e["id"]: score_expert(e, brief) for e in load_experts()}


# Specialists any engagement benefits from. These break score ties only, so a
# brief with real signal still gets its subject-matter match — but a brief that
# scores flat gets fact-checking and user voice rather than the lowest id.
_BENCH_PREFERENCE = ("L1-025", "L1-030", "L1-026", "L1-031", "L1-029")
_PREF_RANK = {eid: i for i, eid in enumerate(_BENCH_PREFERENCE)}


def _ranked(pool: Iterable[Dict], scores: Dict[str, int]) -> List[Dict]:
    """Highest score first; a curated bench order and then id break ties, so
    staffing is reproducible for the same brief."""
    return sorted(
        pool,
        key=lambda e: (
            -scores.get(e["id"], 0),
            _PREF_RANK.get(e["id"], len(_BENCH_PREFERENCE)),
            e["id"],
        ),
    )


def shortlist(
    scores: Dict[str, int], *, industry: int = 8, function: int = 6
) -> List[Dict]:
    """Candidates to offer the dispatch model.

    All nine L2s are kept — the pool is small enough that filtering it only
    loses signal — alongside the best-matching industry and function
    specialists. That is roughly half the roster, with the profiles that could
    not plausibly serve the brief removed before they cost tokens.
    """
    picked = (
        experts_by_level("L2")
        + _ranked([e for e in experts_by_group("industry") if e["level"] == "L1"], scores)[:industry]
        + _ranked([e for e in experts_by_group("function") if e["level"] == "L1"], scores)[:function]
    )
    return _ranked(picked, scores)


# ── Team composition ──────────────────────────────────────────────────────────
def _fill_reason(e: Dict, need: str) -> str:
    return f"Staffed by the composition check — {e['role_title']}, {need}"


def normalize_team(
    members: Sequence[Dict[str, str]], scores: Dict[str, int]
) -> List[Dict[str, str]]:
    """Repair whatever the dispatch model returned into a workable team.

    Drops unknown and duplicate ids, enforces the size bounds, guarantees the
    permanent L3s, at least one strategy advisor and at least one function
    specialist to run collection, then tops the specialist bench up from the
    best-scoring profiles left.
    """
    roster = {e["id"]: e for e in load_experts()}

    seen: set[str] = set()
    picked: List[Dict[str, str]] = []
    for m in members:
        if not isinstance(m, dict):
            continue
        eid = m.get("id")
        # L3s are permanent staff and are added below; a model that named one
        # anyway should not consume an L2 or L1 slot with it.
        if eid not in roster or eid in seen or eid in PERMANENT_L3:
            continue
        seen.add(eid)
        picked.append({"id": eid, "reason": str(m.get("reason", "")).strip()})

    l2 = [m for m in picked if roster[m["id"]]["level"] == "L2"]
    l1 = [m for m in picked if roster[m["id"]]["level"] == "L1"]

    def _drop_weakest(rows: List[Dict[str, str]], keep: int) -> List[Dict[str, str]]:
        if len(rows) <= keep:
            return rows
        strongest = {
            m["id"] for m in
            sorted(rows, key=lambda m: (-scores.get(m["id"], 0), m["id"]))[:keep]
        }
        return [m for m in rows if m["id"] in strongest]  # model order preserved

    l2 = _drop_weakest(l2, MAX_L2)
    l1 = _drop_weakest(l1, MAX_L1)

    def _add(pool: Iterable[Dict], need: str, rows: List[Dict[str, str]]) -> bool:
        for e in _ranked(pool, scores):
            if e["id"] in seen:
                continue
            seen.add(e["id"])
            rows.append({"id": e["id"], "reason": _fill_reason(e, need)})
            return True
        return False

    while len(l2) < MIN_L2:
        if not _add(experts_by_level("L2"), "the brief needed a strategy read", l2):
            break

    # Collection tradecraft is needed whatever the subject is, so a team with no
    # function specialist is malformed regardless of how good its industry
    # coverage looks.
    has_function = any(roster[m["id"]]["group"] == "function" for m in l1)
    if not has_function:
        _add(
            [e for e in experts_by_group("function") if e["level"] == "L1"],
            "no one on the team was staffed to run collection",
            l1,
        )

    while len(l1) < MIN_L1:
        if not _add(
            [e for e in load_experts() if e["level"] == "L1"],
            "the specialist bench was short",
            l1,
        ):
            break

    l1 = _drop_weakest(l1, MAX_L1)

    leads = [{"id": eid, "reason": _L3_REASONS[eid]} for eid in PERMANENT_L3]
    return leads + l2 + l1


# ── Stage routing ─────────────────────────────────────────────────────────────
# What each stage's tradecraft actually looks like in a profile, so the crawler
# gets collection and the social listener gets sentiment rather than whoever
# happens to sort first. Matched as substrings against tags, skills and title.
_STAGE_AFFINITY = {
    "collect": (
        "content extraction", "source discovery", "robots", "canonical",
        "rate limiting", "crawl", "collection", "archiving", "provenance",
        "web data",
    ),
    "sentiment": (
        "sentiment", "social", "reddit", "hacker news", "community", "review",
        "qualitative", "thematic", "verbatim", "astroturf", "listening",
    ),
}
# The purpose-built specialist for each, used when they are on the team.
_STAGE_PREFERRED = {"collect": "L1-025", "sentiment": "L1-030"}


def _affinity(e: Dict, terms: Sequence[str]) -> int:
    hay = " ".join(
        [*e.get("knowledge_tags", []), *e.get("skills", []), e.get("role_title", "")]
    ).lower()
    return sum(1 for t in terms if t in hay)


def _pick_stage(pool: List[Dict], stage: str, default: str) -> str:
    if not pool:
        return default
    preferred = _STAGE_PREFERRED.get(stage)
    if preferred and any(e["id"] == preferred for e in pool):
        return preferred
    terms = _STAGE_AFFINITY.get(stage, ())
    ranked = sorted(pool, key=lambda e: (-_affinity(e, terms), e["id"]))
    return ranked[0]["id"]


def assign_stages(member_ids: Sequence[str], focus: Sequence[str]) -> Dict[str, str]:
    """Map pipeline stage -> expert id, by capability rather than id prefix.

    Also returns `industry`: the best-matching industry analyst on the team,
    which `section_writer` uses for the sections that are really a read on the
    market rather than on the product.
    """
    members = [e for e in (expert_by_id(m) for m in member_ids) if e]
    l1 = [e for e in members if e["level"] == "L1"]
    l2 = [e for e in members if e["level"] == "L2"]
    function = [e for e in l1 if e["group"] == "function"]
    industry = [e for e in l1 if e["group"] == "industry"]

    collect = _pick_stage(function or l1, "collect", "L1-025")
    sentiment = _pick_stage(function or l1, "sentiment", collect)

    # The strategy advisor whose specialism best fits what the brief prioritizes
    # — a pricing-heavy focus lands on the pricing strategist, a filings-heavy
    # one on the financial analyst.
    brief = _tokens(" ".join(focus))
    analyze = (
        sorted(l2, key=lambda e: (-score_expert(e, brief), e["id"]))[0]["id"]
        if l2 else "L2-001"
    )
    best_industry = (
        sorted(industry, key=lambda e: (-score_expert(e, brief), e["id"]))[0]["id"]
        if industry else ""
    )

    return {
        "intake": DIRECTOR,
        "orchestrator": DIRECTOR,
        "done": DIRECTOR,
        "collect": collect,
        "sentiment": sentiment,
        "analyze": analyze,
        "audit": QUALITY,
        "verify": QUALITY,
        "write": CHIEF_ANALYST,
        "industry": best_industry,
    }


# ── Section authorship ────────────────────────────────────────────────────────
# Which specialism should argue each section, in preference order. The first id
# actually on the team wins; anything unclaimed goes to the chief analyst, who
# owns authorship.
SECTION_AFFINITY: Dict[str, tuple[str, ...]] = {
    "feature": ("L2-006", "L2-001"),        # architecture, then strategy
    "pricing": ("L2-002", "L2-005"),        # pricing strategist, then finance
    "persona": ("L2-003", "L1-029"),        # user research, then interviews
    "swot": ("L2-001", "L2-004"),           # strategy, then competitive intel
    "risk": ("L2-009", "L2-005"),           # compliance, then finance
    "persp_pm": ("L2-006", "L2-003"),
    "persp_ops": ("L2-006", "L2-009"),
    "persp_sales": ("L2-007", "L2-002"),
    "persp_user": ("L2-003", "L1-029"),
    "persp_investor": ("L2-005", "L2-001"),
}

# Sections that are a read on the market rather than on the product, and so
# belong to the industry analyst when the team has one.
_INDUSTRY_SECTIONS = frozenset({"trend", "inflection"})


def section_writer(
    sid: str, member_ids: Sequence[str], stages: Dict[str, str]
) -> str:
    """Who argues one section. Falls back to the chief analyst."""
    on_team = set(member_ids)
    for cand in SECTION_AFFINITY.get(sid, ()):
        if cand in on_team:
            return cand
    if sid in _INDUSTRY_SECTIONS and stages.get("industry"):
        return stages["industry"]
    return CHIEF_ANALYST
