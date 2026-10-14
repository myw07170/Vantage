"""Staffing and persona building.

No API key needed — every function under test is deterministic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.personas import (
    CHIEF_ANALYST,
    DIRECTOR,
    GROUNDING_GUARD,
    MAX_L1,
    MAX_L2,
    MIN_L1,
    PERMANENT_L3,
    QUALITY,
    PERMANENT_TEAM,
    TEAM_BOUNDS,
    assign_stages,
    normalize_team,
    persona_block,
    score_roster,
    section_writer,
    shortlist,
    select_industry_modules,
    module_search_angles,
    team_block,
)
from app.data import active_experts, expert_by_id, load_experts, load_industry_modules

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROSTER = ROOT / "backend" / "app" / "data" / "experts.json"
FRONTEND_ROSTER = ROOT / "frontend" / "public" / "assets" / "experts.json"


def _ids(members):
    return [m["id"] for m in members]


def _level(eid):
    return (expert_by_id(eid) or {})["level"]


# ── Roster integrity ──────────────────────────────────────────────────────────
def test_roster_ids_unique_and_keys_consistent():
    roster = load_experts()
    ids = [e["id"] for e in roster]
    assert len(ids) == len(set(ids))
    keys = set(roster[0])
    assert all(set(e) == keys for e in roster)


def test_every_expert_has_enough_tags_to_be_matchable():
    # The shortlist scorer matches on tags; a thin profile is unreachable.
    for e in load_experts():
        assert len(e["knowledge_tags"]) >= 6, e["id"]


# Portraits for the four analysts added alongside the persona work have not
# been drawn. VAvatar degrades to initials (VAvatar.tsx:100), so the roster
# ships without them — but the gap is named here rather than ignored, and
# `test_pending_avatars_is_not_stale` forces this list to be emptied once the
# images land.
PENDING_AVATARS = {"L1-037", "L1-038", "L1-039", "L1-040"}


def _avatar_path(e):
    return ROOT / "frontend" / "public" / e["avatar"].lstrip("/")


def test_avatars_resolve():
    for e in load_experts():
        if e["id"] in PENDING_AVATARS:
            continue
        assert _avatar_path(e).exists(), f"{e['id']} avatar missing: {e['avatar']}"


def test_pending_avatars_is_not_stale():
    landed = {
        e["id"] for e in load_experts()
        if e["id"] in PENDING_AVATARS and _avatar_path(e).exists()
    }
    assert not landed, f"avatars now exist; drop from PENDING_AVATARS: {sorted(landed)}"


def test_domain_icons_resolve():
    icons = (ROOT / "frontend" / "src" / "components" / "DomainIcon.tsx").read_text(
        encoding="utf-8"
    )
    for e in load_experts():
        slug = e["domain_icon"]
        assert f"{slug}:" in icons or f"'{slug}':" in icons, f"{e['id']} icon {slug}"


def test_frontend_roster_copy_is_in_sync():
    # The frontend copy is the offline fallback; a drifted copy ships a
    # different team than the backend staffs.
    assert json.loads(BACKEND_ROSTER.read_text(encoding="utf-8")) == json.loads(
        FRONTEND_ROSTER.read_text(encoding="utf-8")
    )


# ── Persona blocks ────────────────────────────────────────────────────────────
def test_persona_block_carries_profile_and_guard():
    block = persona_block(QUALITY)
    qc = expert_by_id(QUALITY)
    assert qc["name"] in block
    assert qc["role_title"] in block
    assert "circular reporting" in block
    assert "Deliver:" in block and "Boundary:" in block
    assert qc["knowledge_base"] not in block  # display biography is not the execution prompt
    assert GROUNDING_GUARD in block


def test_persona_block_is_empty_for_unknown_id():
    # Call sites prepend unconditionally, so an unknown id must degrade to the
    # generic voice rather than raise.
    assert persona_block("nope") == ""
    assert team_block([]) == ""


def test_team_block_names_every_member():
    ids = [DIRECTOR, "L2-002", "L1-008"]
    block = team_block(ids)
    for eid in ids:
        assert expert_by_id(eid)["name"] in block
    assert GROUNDING_GUARD in block


# ── Scoring and shortlist ─────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "query, expected",
    [
        ("Okta vs Auth0 vs Entra ID for mid-market SSO", "L1-037"),
        ("Stripe vs Adyen payment processing for fintech", "L1-001"),
        ("Steam vs Epic Games Store revenue share", "L1-010"),
        ("AWS vs Azure vs GCP cloud infrastructure", "L1-007"),
    ],
)
def test_matching_puts_the_right_industry_module_on_top(query, expected):
    assert select_industry_modules(query, [], [])[0]["legacy_expert_id"] == expected


def test_shortlist_contains_only_active_optional_strategy_roles():
    scores = score_roster("identity and access management", [], [])
    picked = shortlist(scores)
    ids = {e["id"] for e in picked}
    assert ids == {e["id"] for e in active_experts() if e["level"] == "L2"}
    assert len(picked) == 7
    assert "L2-004" not in ids and "L2-008" not in ids


# ── Composition repair ────────────────────────────────────────────────────────
def test_normalize_team_repairs_a_malformed_dispatch():
    scores = score_roster("cybersecurity posture management", [], [])
    # Eight L1 industry analysts, no strategy advisor, no function specialist.
    malformed = [
        {"id": f"L1-{n:03d}", "reason": "r"} for n in range(1, 9)
    ]
    team = _ids(normalize_team(malformed, scores))

    assert team[:3] == list(PERMANENT_L3)
    l1 = [e for e in team if _level(e) == "L1"]
    l2 = [e for e in team if _level(e) == "L2"]
    assert 1 <= len(l2) <= MAX_L2
    assert MIN_L1 <= len(l1) <= MAX_L1
    assert any(expert_by_id(e)["group"] == "function" for e in l1)
    assert len(team) == len(set(team))


def test_normalize_team_drops_unknown_ids_and_model_chosen_l3s():
    scores = score_roster("saas pricing", [], [])
    team = _ids(normalize_team(
        [
            {"id": "L9-999", "reason": "does not exist"},
            {"id": DIRECTOR, "reason": "already permanent staff"},
            {"id": "L2-002", "reason": "pricing"},
            {"id": "L2-002", "reason": "duplicate"},
        ],
        scores,
    ))
    assert "L9-999" not in team
    assert team.count(DIRECTOR) == 1
    assert team.count("L2-002") == 1


def test_normalize_team_builds_a_full_team_from_nothing():
    # The dispatch call returning nothing must still yield a workable team.
    scores = score_roster("compare project management tools", [], [])
    team = _ids(normalize_team([], scores))
    assert set(PERMANENT_L3) <= set(team)
    assert len([e for e in team if _level(e) == "L2"]) >= 1
    assert len([e for e in team if _level(e) == "L1"]) >= MIN_L1


def test_staffing_is_reproducible():
    scores = score_roster("EV charging networks", [], [])
    assert _ids(normalize_team([], scores)) == _ids(normalize_team([], scores))


# ── Stage routing ─────────────────────────────────────────────────────────────
def test_stages_route_to_the_purpose_built_specialist():
    # A team where the crawler and social listener are not first in the list.
    members = [*PERMANENT_L3, "L2-001", "L1-004", "L1-032", "L1-025", "L1-030"]
    stages = assign_stages(members, ["pricing"])
    assert stages["collect"] == "L1-025"      # not L1-004, the first L1
    assert stages["sentiment"] == "L1-030"    # not L1-032, the first function member
    assert stages["audit"] == stages["verify"] == QUALITY
    assert stages["intake"] == DIRECTOR
    assert stages["industry"] == "L2-001"


def test_fixed_collection_ownership_never_uses_archived_industry_roles():
    stages = assign_stages([*PERMANENT_L3, "L2-001", "L1-004"], [])
    assert stages["collect"] == "L1-025"
    assert stages["sentiment"] == "L1-030"


def test_analyze_goes_to_the_advisor_matching_the_focus():
    members = [*PERMANENT_L3, "L2-001", "L2-002", "L1-002"]
    assert assign_stages(members, ["pricing and packaging"])["analyze"] == "L2-002"
    assert assign_stages(members, ["market structure and moats"])["analyze"] == "L2-001"


# ── Section authorship ────────────────────────────────────────────────────────
def test_sections_go_to_the_analyst_who_owns_the_subject():
    members = [*PERMANENT_L3, "L2-002", "L2-009", "L1-008"]
    stages = assign_stages(members, [])
    assert section_writer("pricing", members, stages) == "L2-002"
    assert section_writer("risk", members, stages) == "L2-009"
    assert section_writer("trend", members, stages) == CHIEF_ANALYST
    # Unclaimed and team-independent sections stay with the chief analyst.
    assert section_writer("summary", members, stages) == CHIEF_ANALYST
    assert section_writer("feature", members, stages) == CHIEF_ANALYST


def test_section_writer_falls_back_when_the_specialist_is_not_staffed():
    members = [*PERMANENT_L3, "L2-001"]
    stages = assign_stages(members, [])
    assert section_writer("pricing", members, stages) == CHIEF_ANALYST
    assert section_writer("trend", members, stages) == "L2-001"


def test_core_catalog_and_archived_identities_are_separate():
    assert len(active_experts()) == 12
    assert len(load_experts()) == 52
    assert len(load_industry_modules()) == 28
    assert expert_by_id("L1-008")["catalog_status"] == "archived"
    assert all(e["work_instructions"]["limits"] for e in active_experts())
    root = ROOT / "frontend/public/assets/industry_modules.json"
    assert json.loads(root.read_text(encoding="utf-8")) == load_industry_modules()
    assert len({m["id"] for m in load_industry_modules()}) == 28


@pytest.mark.parametrize("mode", ["quick", "deep", "expert"])
def test_mode_bounds_repair_empty_and_overstaffed_teams(mode):
    scores = score_roster("SaaS pricing and financial statements", [], [])
    candidates = [{"id": e["id"], "reason": ""} for e in load_experts()]
    candidates += [{"id": ["invalid"], "reason": ""}, {"id": "unknown"}, None]
    minimum, maximum = TEAM_BOUNDS[mode]
    for members, expected in (([], minimum), (candidates, maximum)):
        team = normalize_team(members, scores, mode)
        ids = _ids(team)
        assert len(ids) == 5 + expected
        assert len(set(ids)) == len(ids) and set(PERMANENT_TEAM) <= set(ids)
        assert all(expert_by_id(eid)["catalog_status"] == "active" for eid in ids)
        assert all(m["reason"] for m in team)


@pytest.mark.parametrize("query, expected", [
    ("pricing packaging and tier fencing", "L2-002"),
    ("architecture scalability API integration", "L2-006"),
    ("privacy regulatory compliance risk", "L2-009"),
    ("financial statements unit economics valuation", "L2-005"),
    ("user research personas segmentation", "L2-003"),
])
def test_strategy_matching_covers_core_decision_needs(query, expected):
    scores = score_roster(query, [], [])
    assert shortlist(scores)[0]["id"] == expected


def test_industry_methods_no_match_two_matches_and_snapshot_isolation():
    assert select_industry_modules("compare A and B", [], []) == []
    modules = select_industry_modules("cloud infrastructure cybersecurity identity SSO", [], [])
    assert len(modules) == 2
    assert {m["legacy_expert_id"] for m in modules} == {"L1-007", "L1-037"}
    modules[0]["checks"].append("a local edit")
    assert all("a local edit" not in m["checks"] for m in load_industry_modules())


def test_module_angles_fit_budget_and_preserve_recency():
    modules = select_industry_modules("cloud infrastructure", [], [])[:1]
    angles = module_search_angles(["product features", "pricing plans", "user reviews", "latest news"], modules, 4)
    assert len(angles) == 4 and "latest news" in angles
    assert set(modules[0]["search_angles"]) <= set(angles)
    overlap = module_search_angles(["features", "pricing", "latest news", *modules[0]["search_angles"]], modules, 4)
    assert set(modules[0]["search_angles"]) <= set(overlap) and len(set(overlap)) == len(overlap) == 4
    assert module_search_angles(["pricing", "latest news"], [], 4) == ["pricing", "latest news"]
    assert select_industry_modules("compare A and B", [], ["Feature comparison", "Pricing strategy", "User sentiment"]) == []


def test_team_and_personal_prompts_include_actions_and_industry_checks():
    modules = select_industry_modules("cloud infrastructure", [], [])
    for block in (persona_block("L2-002", modules), team_block([DIRECTOR, "L2-002"], industry_modules=modules)):
        assert "billing period" in block
        assert modules[0]["checks"][0] in block
        assert GROUNDING_GUARD in block and "American English" in block
        assert "explicit market always takes precedence" in block
