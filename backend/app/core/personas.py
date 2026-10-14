"""Core analyst staffing, archived identities and industry research methods."""
from __future__ import annotations

import copy
import re
from typing import Dict, Iterable, List, Sequence

from app.data import active_experts, expert_by_id, experts_by_level, load_industry_modules

DIRECTOR = "L3-001"
CHIEF_ANALYST = "L3-002"
QUALITY = "L3-003"
COLLECTOR = "L1-025"
USER_FEEDBACK = "L1-030"
PERMANENT_L3 = (DIRECTOR, CHIEF_ANALYST, QUALITY)
PERMANENT_TEAM = (*PERMANENT_L3, COLLECTOR, USER_FEEDBACK)
TEAM_BOUNDS = {"quick": (1, 2), "deep": (2, 3), "expert": (3, 4)}
MIN_L2, MAX_L2 = TEAM_BOUNDS["deep"]
MIN_L1 = MAX_L1 = 2

_FIXED_REASONS = {
    DIRECTOR: "Owns the confirmed scope, research plan and final sign-off.",
    CHIEF_ANALYST: "Owns cross-section reasoning, report integration and recommendations.",
    QUALITY: "Checks citations, statistical definitions and bias; requests evidence-specific rework.",
    COLLECTOR: "Owns public evidence discovery, extraction and source provenance.",
    USER_FEEDBACK: "Owns collected reviews, community feedback and sample limitations.",
}
GROUNDING_GUARD = (
    "Your background shapes which sources you reach for and what you "
    "interrogate. It never licenses a claim the evidence below does not support."
)
RESEARCH_POLICY = (
    "Write all generated content in American English. Use the U.S. market as "
    "the default when the confirmed request does not specify a market or says No preference; an "
    "explicit market always takes precedence. Preserve source quotations and "
    "product names accurately. Use only the supplied evidence and available "
    "public collection tools; source preferences do not imply database access."
)
_INSTRUCTION_LABELS = {
    "responsibilities": "Responsibility", "preferred_sources": "Preferred evidence",
    "checks": "Check", "deliverables": "Deliver", "limits": "Boundary",
}


def _work_block(e: Dict) -> str:
    instructions = e.get("work_instructions") or {}
    return "\n".join(f"{label}: {item}" for key, label in _INSTRUCTION_LABELS.items()
                     for item in instructions.get(key, []))


def industry_block(modules: Sequence[Dict] | None = None) -> str:
    if not modules:
        return ""
    rows = ["Industry methods for this engagement (not findings or extra analysts):"]
    for module in modules:
        rows.append(f"- {module['name']}: {module.get('summary', '')}")
        for key, label in (("preferred_sources", "Prefer"), ("checks", "Check"),
                           ("search_angles", "Search direction")):
            rows.extend(f"  {label}: {item}" for item in module.get(key, []))
    rows.append("Apply these methods only to the confirmed products and supplied evidence.")
    return "\n".join(rows) + "\n\n"


def persona_block(eid: str, industry_modules: Sequence[Dict] | None = None) -> str:
    e = expert_by_id(eid)
    if not e:
        return ""
    rows = [f"You are {e['name']}, {e['role_title']}, on this engagement."]
    work = _work_block(e)
    if work:
        rows.append(work)
    elif e.get("one_liner"):
        # Old reports may still be refined using their historical author.
        rows.append(e["one_liner"])
    rows.extend((GROUNDING_GUARD, RESEARCH_POLICY))
    return "\n".join(rows) + "\n\n" + industry_block(industry_modules)


def team_block(member_ids: Sequence[str], limit: int = 12,
               industry_modules: Sequence[Dict] | None = None) -> str:
    rows = []
    for eid in list(member_ids)[:limit]:
        e = expert_by_id(eid)
        if e:
            rows.append(f"- {e['name']}, {e['role_title']}\n{_work_block(e) or e.get('one_liner', '')}")
    if not rows:
        return ""
    return ("You are the analysis team staffed on this engagement:\n"
            + "\n".join(rows) + "\n" + GROUNDING_GUARD + "\n" + RESEARCH_POLICY
            + "\n\n" + industry_block(industry_modules))


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "over", "than",
    "versus", "compare", "comparison", "competitive", "competitor", "competitors",
    "analysis", "analyst", "market", "product", "products", "company", "companies",
    "business", "research", "report", "data", "best", "top", "how", "what", "why",
    "who", "which", "does", "are", "its", "their", "our", "new", "use", "using",
}


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall((text or "").lower())
            if len(t) > 2 and t not in _STOPWORDS}


def score_expert(e: Dict, brief: set[str]) -> int:
    if not brief:
        return 0
    score = sum(3 for tag in e.get("knowledge_tags", []) if _tokens(tag) & brief)
    score += sum(2 for skill in e.get("skills", []) if _tokens(skill) & brief)
    score += 2 if _tokens(e.get("role_title", "")) & brief else 0
    return score + min(len(_tokens(e.get("knowledge_base", "")) & brief), 4)


def score_roster(query: str, brands: Sequence[str], focus: Sequence[str]) -> Dict[str, int]:
    brief = _tokens(" ".join([query, *brands, *focus]))
    return {e["id"]: score_expert(e, brief) for e in active_experts()}


def _ranked(pool: Iterable[Dict], scores: Dict[str, int]) -> List[Dict]:
    return sorted(pool, key=lambda e: (-scores.get(e["id"], 0), e["id"]))


def shortlist(scores: Dict[str, int]) -> List[Dict]:
    """Only the seven optional strategy roles need a model selection."""
    return _ranked(experts_by_level("L2"), scores)


def select_industry_modules(query: str, brands: Sequence[str], focus: Sequence[str],
                            category: str = "") -> List[Dict]:
    brief = _tokens(" ".join([category, query, *brands, *focus]))
    # A request for pricing or user reviews alone does not identify an industry.
    brief -= {"pricing", "price", "prices", "feature", "features", "user", "users",
              "sentiment", "review", "reviews", "strategy", "strategies", "latest",
              "news", "overview", "trend", "trends", "focus"}
    modules = load_industry_modules()
    scores = {m["id"]: score_expert({**m, "role_title": m["name"]}, brief) for m in modules}
    return [copy.deepcopy(m) for m in _ranked(modules, scores) if scores[m["id"]] > 0][:2]


def module_search_angles(angles: Sequence[str], modules: Sequence[Dict], limit: int) -> List[str]:
    """Reserve two directions within the existing search budget."""
    base = list(dict.fromkeys(angles))
    extra = list(dict.fromkeys(a for i in range(2) for m in modules
                              for a in m.get("search_angles", [])[i:i + 1]))[:min(2, limit)]
    if not extra:
        return base[:limit]
    general = [a for a in base if a not in extra][:limit - len(extra)]
    recent = next((a for a in base if re.search(r"latest|recent|release|news", a, re.I)), None)
    if recent and general and recent not in general:
        general[-1] = recent
    return (general + extra)[:limit]


def normalize_team(members: Sequence[Dict[str, str]], scores: Dict[str, int],
                   mode: str = "deep") -> List[Dict[str, str]]:
    minimum, maximum = TEAM_BOUNDS.get(mode, TEAM_BOUNDS["deep"])
    eligible = {e["id"]: e for e in experts_by_level("L2")}
    picked = {}
    for member in members:
        if not isinstance(member, dict):
            continue
        eid = member.get("id")
        if isinstance(eid, str) and eid in eligible and eid not in picked:
            picked[eid] = {"id": eid, "reason": str(member.get("reason") or "").strip()}
    strongest = sorted(picked, key=lambda eid: (-scores.get(eid, 0), eid))[:maximum]
    selected = [picked[eid] for eid in strongest]
    for e in _ranked(eligible.values(), scores):
        if len(selected) >= minimum:
            break
        if e["id"] not in strongest:
            selected.append({"id": e["id"], "reason": ""})
    for member in selected:
        if not member["reason"]:
            e = eligible[member["id"]]
            member["reason"] = "Matched to the brief: " + e["work_instructions"]["responsibilities"][0]
    return ([{"id": eid, "reason": _FIXED_REASONS[eid]} for eid in PERMANENT_L3]
            + selected
            + [{"id": eid, "reason": _FIXED_REASONS[eid]} for eid in (COLLECTOR, USER_FEEDBACK)])


def assign_stages(member_ids: Sequence[str], focus: Sequence[str]) -> Dict[str, str]:
    l2 = [e for eid in member_ids if (e := expert_by_id(eid))
          and e.get("catalog_status") == "active" and e["level"] == "L2"]
    brief = _tokens(" ".join(focus))
    analyst = sorted(l2, key=lambda e: (-score_expert(e, brief), e["id"]))[0]["id"] if l2 else CHIEF_ANALYST
    market = next((eid for eid in ("L2-001", "L2-005") if eid in member_ids), CHIEF_ANALYST)
    return {"intake": DIRECTOR, "orchestrator": DIRECTOR, "done": DIRECTOR,
            "collect": COLLECTOR, "sentiment": USER_FEEDBACK, "analyze": analyst,
            "audit": QUALITY, "verify": QUALITY, "write": CHIEF_ANALYST, "industry": market}


SECTION_AFFINITY = {
    "feature": ("L2-006", "L2-001"), "pricing": ("L2-002", "L2-005"),
    "persona": ("L2-003", USER_FEEDBACK), "swot": ("L2-001",),
    "risk": ("L2-009", "L2-005"), "persp_pm": ("L2-006", "L2-003"),
    "persp_ops": ("L2-006", "L2-009"), "persp_sales": ("L2-007", "L2-002"),
    "persp_user": ("L2-003", USER_FEEDBACK), "persp_investor": ("L2-005", "L2-001"),
}


def section_writer(sid: str, member_ids: Sequence[str], stages: Dict[str, str]) -> str:
    on_team = {eid for eid in member_ids if (e := expert_by_id(eid)) and e.get("catalog_status") == "active"}
    for eid in SECTION_AFFINITY.get(sid, ()):
        if eid in on_team:
            return eid
    if sid in ("trend", "inflection"):
        return stages.get("industry", CHIEF_ANALYST)
    return CHIEF_ANALYST
