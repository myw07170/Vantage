"""Deep Research orchestration engine.

Pipeline: intake -> orchestrator -> collect -> analyze -> write -> audit
          -> (pass / rework) -> done

Operating principles:

* **Real collection.** Every competitor is searched from multiple angles and
  the resulting pages are actually fetched, not summarized from memory.
* **Real user voice.** Reddit and Hacker News are read through their APIs;
  review sites through site-restricted search. Every quote keeps its link.
* **Nothing fabricated.** If a search returns nothing, the report says so.
  There is no demo data, no placeholder statistics, no invented comments.
* **Real persistence.** Tasks, reports, evidence, expert workload and traces
  all land in SQLite.
* **The four iron rules** run throughout: no claim without evidence,
  cross-validation for high confidence, a rework loop that actually fires, and
  full observability of every model call.

Model routing: the Gemini free tier offers Flash and Flash-Lite only, so the
core and auxiliary tiers share one model and light work goes to Flash-Lite.
Sections are written in parallel; the rate limiter paces the fan-out.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import re
import time
import uuid
from collections import Counter
from typing import Any, AsyncIterator, Dict, List, Optional
from urllib.parse import quote

from app.core import charts as C
from app.core import db
from app.core import trace
from app.core.audit import decide_rework, evaluate_quality, llm_quality_review
from app.core.config import get_settings
from app.core.credibility import freshness_days, score_evidence
from app.core.fetcher import domain_of, fetch_page
from app.core.llm import TOKEN_USAGE, chat, chat_json
from app.core.metrics import compute_report_metrics, merge_quality_into_metrics
from app.core.models import Envelope, Evidence, SourceType, make_claim
from app.core.platforms import (
    PLATFORM_LABEL,
    PLATFORM_SOURCE_TYPE,
    api_platforms,
    search_platforms,
)
from app.core.schemas import (
    coerce_feature_tree,
    coerce_pricing_model,
    coerce_user_persona,
)
from app.core.search import multi_search
from app.core.sentiment import analyze_sentiment
from app.core.textquality import is_relevant_content
from app.data import expert_by_id, load_experts

_settings = get_settings()


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _sid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ── Research modes ────────────────────────────────────────────────────────────
# Each tier scales search angles, fetch depth, section count, rework rounds and
# writing length together.
MODE_CONFIG = {
    "quick": {
        "label": "Quick",
        "max_angles": 4, "fetch_per_brand": 6, "platform_per": 6,
        "sections": ["summary", "overview", "feature", "pricing", "conclusion"],
        "freshness": "year", "rework_rounds": 0,
        "min_paragraphs": 3, "para_words": "90-150", "section_max_tokens": 3500,
        "analyze_max_tokens": 6000, "structured_max_tokens": 6000,
        "sentiment_brands": 2, "platform_take": 5,
    },
    "deep": {
        "label": "Deep",
        "max_angles": 6, "fetch_per_brand": 12, "platform_per": 8,
        "sections": ["summary", "overview", "feature", "pricing", "persona",
                     "trend", "swot", "conclusion", "risk"],
        "freshness": "year", "rework_rounds": 1,
        "min_paragraphs": 5, "para_words": "130-200", "section_max_tokens": 6000,
        "analyze_max_tokens": 8000, "structured_max_tokens": 8000,
        "sentiment_brands": 3, "platform_take": 8,
    },
    "expert": {
        "label": "Expert",
        "max_angles": 9, "fetch_per_brand": 16, "platform_per": 10,
        "sections": ["summary", "overview", "feature", "pricing", "persona",
                     "trend", "swot", "moat", "inflection", "contrarian",
                     "conclusion", "risk"],
        "freshness": "year", "rework_rounds": 2,
        "min_paragraphs": 7, "para_words": "180-300", "section_max_tokens": 9000,
        "analyze_max_tokens": 9000, "structured_max_tokens": 9000,
        "sentiment_brands": 4, "platform_take": 10,
    },
}


def _model(tier: str) -> str:
    """tier: 'core' | 'aux' | 'fast' -> a model name.

    Gemini's free tier has no Pro model, so core and aux both resolve to Flash;
    the three tier names are kept because call sites express intent with them.
    """
    if tier == "fast":
        return _settings.gemini_model_fast
    return _settings.gemini_model_core


# ── Task creation / clarification ─────────────────────────────────────────────
def create_task(query: str, mode: str = "deep") -> Dict[str, Any]:
    task_id = _sid("t")
    questions = _clarify_questions(query)
    db.save_task(task_id, query, {"_mode": mode})
    return {"taskId": task_id, "needClarify": True, "clarifyQuestions": questions}


def submit_clarify(task_id: str, answers: Dict[str, Any]) -> Dict[str, Any]:
    task = db.get_task(task_id) or {}
    prev = task.get("clarifications", {}) or {}
    merged = {**answers}
    if "_mode" in prev and "_mode" not in merged:
        merged["_mode"] = prev["_mode"]
    db.update_task_clarify(task_id, merged)
    return {"ok": True}


def refine_section(
    report_id: str, section_id: str, annotations: List[str]
) -> Dict[str, Any]:
    """Re-deepen one section against a reader's annotations.

    Uses the evidence already gathered for the report, so this costs one model
    call rather than a fresh research run.
    """
    rep = db.get_report(report_id)
    if not rep:
        return {"ok": False, "message": "report not found"}
    sections = rep.get("sections", [])
    target = next((s for s in sections if s.get("id") == section_id), None)
    if not target:
        return {"ok": False, "message": "section not found"}

    query = rep.get("query", "")
    brands = rep.get("brands", [])
    evidence = rep.get("evidence", [])
    digest = "\n".join(
        f"[{e.get('evidence_id')}|{e.get('domain','')}] {e.get('title','')}: {e.get('excerpt','')}"
        for e in evidence[:24]
    )
    note_text = "\n".join(f"- {a}" for a in annotations if a)
    existing = "\n".join(target.get("paragraphs", []))

    try:
        data = chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a senior competitive analyst. A reader has "
                        "annotated one section of your report asking for more "
                        "depth. Rewrite that section to address their notes "
                        "specifically — add argument, data, comparison and your "
                        "own judgement. Keep every factual claim tied to the "
                        "evidence provided.\n"
                        'Return JSON: {"paragraphs":["..."],'
                        '"key_takeaway":"...","highlights":["..."]}'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Section: {target.get('title','')}\n"
                        f"Research topic: {query}\n"
                        f"Competitors: {', '.join(brands)}\n\n"
                        f"Reader's annotations:\n{note_text}\n\n"
                        f"Current section text:\n{existing}\n\n"
                        f"Available evidence:\n{digest}"
                    ),
                },
            ],
            max_tokens=6000,
            temperature=0.7,
            model=_model("core"),
            purpose=f"Deepen section from annotations: {target.get('title','')}",
        )
        if isinstance(data, dict) and data.get("paragraphs"):
            paras = [str(p).strip() for p in data["paragraphs"] if str(p).strip()]
            if paras:
                target["paragraphs"] = paras
                if data.get("key_takeaway"):
                    target["key_takeaway"] = str(data["key_takeaway"])
                hl = data.get("highlights")
                if isinstance(hl, list):
                    target["highlights"] = [str(h) for h in hl if str(h).strip()]
                target["refined"] = True
                db.save_report(rep, task_id="")
                return {"ok": True, "section": target}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": str(e)}
    return {"ok": False, "message": "refine failed"}


def _clarify_questions(query: str) -> List[Dict[str, Any]]:
    """Scope discovery first, then the clarification questionnaire.

    Discovering candidate competitors up front and letting the user tick them
    is what prevents the common failure where a request to "research X" returns
    a report about X alone with no comparison at all.
    """
    scope = _discover_scope(query)
    subject = scope.get("subject") or query
    domain = scope.get("domain") or ""
    competitors = scope.get("competitors") or []

    questions: List[Dict[str, Any]] = []
    if domain:
        questions.append(
            {
                "id": "scope",
                "question": (
                    f"We read this as research on \"{subject}\" in the {domain} "
                    "category. Is that right?"
                ),
                "type": "single",
                "options": [
                    "Yes, continue",
                    "Roughly right — I'll refine below",
                    "No, I'll explain at the end",
                ],
                "hint": "If this is off, describe the real subject in the last question.",
            }
        )
    if competitors:
        questions.append(
            {
                "id": "competitors",
                "question": (
                    f"We found these competitors for \"{subject}\". "
                    "Select the ones you want compared:"
                ),
                "type": "multi",
                "options": competitors[:12],
                "hint": "Everything you select gets researched in full. Add any we missed at the end.",
            }
        )

    questions.extend(
        [
            {
                "id": "focus",
                "question": "Which dimensions matter most for this research?",
                "type": "multi",
                "options": [
                    "Feature comparison", "Pricing strategy", "User sentiment",
                    "Market share", "SWOT", "Growth trends", "Technical architecture",
                    "Business model", "Ecosystem and lock-in", "Positioning",
                ],
            },
            {
                "id": "perspective",
                "question": "Whose perspective should the report be written from?",
                "type": "single",
                "options": [
                    "Product manager", "Growth / marketing", "Sales",
                    "Buyer / end user", "Investor", "General",
                ],
                "hint": (
                    "Each perspective adds a dedicated section — sales gets "
                    "battlecards and objection handling, investors get a moat "
                    "and growth assessment."
                ),
            },
            {
                "id": "market",
                "question": "Which market should we focus on?",
                "type": "single",
                "options": [
                    "United States", "North America", "Global",
                    "EMEA", "APAC", "No preference",
                ],
            },
            {
                "id": "user",
                "question": "Who is the target customer?",
                "type": "single",
                "options": [
                    "Individual consumers", "SMB teams", "Mid-market",
                    "Enterprise", "Developers", "Education", "No preference",
                ],
            },
            {
                "id": "freshness",
                "question": "How recent does the evidence need to be?",
                "type": "single",
                "options": [
                    "Prioritize the last month",
                    "Within the last year",
                    "No time limit",
                ],
            },
            {
                "id": "extra",
                "question": (
                    "Any other competitors, background or corrections we should "
                    "know about? (optional)"
                ),
                "type": "text",
                "options": [],
            },
        ]
    )
    return questions


def _discover_scope(query: str) -> Dict[str, Any]:
    """Identify the subject, its category, and candidate competitors."""
    msgs = [
        {
            "role": "system",
            "content": (
                "You are a competitive research director doing pre-brief scoping. "
                "From a one-line request, determine:\n"
                "1. the actual subject — the full product or company name;\n"
                "2. the category or market segment it competes in;\n"
                "3. 8-12 real, directly competing products or companies, ordered "
                "by prominence.\n\n"
                "Competitors must be real and searchable. Never invent a name to "
                "fill the list — a short accurate list beats a long padded one. "
                "Do not include the subject itself.\n"
                'Return JSON: {"subject":"...","domain":"...","competitors":["..."]}'
            ),
        },
        {"role": "user", "content": query},
    ]
    for _ in range(2):
        try:
            data = chat_json(
                msgs,
                max_tokens=1500,
                temperature=0.3,
                model=_model("aux"),
                purpose="Scope discovery: subject, category, competitors",
            )
            if isinstance(data, dict) and (data.get("subject") or data.get("competitors")):
                subject = str(data.get("subject") or "").strip()
                domain = str(data.get("domain") or "").strip()
                comps = [
                    str(c).strip()
                    for c in (data.get("competitors") or [])
                    if str(c).strip() and str(c).strip() != subject
                ]
                seen = set()
                comps = [c for c in comps if not (c in seen or seen.add(c))]
                return {"subject": subject, "domain": domain, "competitors": comps[:12]}
        except Exception:
            pass
    return {"subject": "", "domain": "", "competitors": []}


def _plan_research(
    query: str, clar: Dict[str, Any], max_angles: int = 7
) -> Dict[str, Any]:
    clar = clar or {}
    clar_text = "; ".join(
        f"{k}: {v}" for k, v in clar.items() if v and not str(k).startswith("_")
    )
    user_brands = clar.get("competitors") or []
    if isinstance(user_brands, str):
        user_brands = [user_brands]
    user_brands = [str(b).strip() for b in user_brands if str(b).strip()]
    try:
        data = chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a competitive research director. Break the request "
                        "into a research plan.\n\n"
                        'Return JSON: {"subject":"full name of the primary subject",'
                        '"category":"the specific category, used to disambiguate '
                        'the name — e.g. \'AI coding assistant\', \'knowledge '
                        "management software', 'electric vehicles'\","
                        '"brands":["competitor 1","competitor 2"],'
                        '"focus":["dimensions to prioritize"],'
                        '"search_angles":["angle phrases appended to each brand, '
                        "e.g. 'pricing plans', 'user reviews', 'product features', "
                        "'2026 latest news', 'market share', 'revenue'\"]}\n\n"
                        "`brands` must contain real, searchable names AND must "
                        "include both the subject itself and its main competitors "
                        "(3-6 total). A report on one company with no comparison "
                        "is a failed report.\n"
                        f"Give {max_angles} search angles, including at least one "
                        "recency angle so current data surfaces."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Research request: {query}\n"
                        f"User's answers: {clar_text or 'none'}\n"
                        "Competitors the user explicitly selected (all must appear "
                        f"in brands): {', '.join(user_brands) or 'none'}"
                    ),
                },
            ],
            max_tokens=2000,
            temperature=0.3,
            model=_model("fast"),
            purpose="Plan research: competitors, dimensions, search angles",
        )
        if isinstance(data, dict) and (data.get("brands") or user_brands):
            llm_brands = [
                b for b in (data.get("brands") or []) if isinstance(b, str) and b.strip()
            ]
            subject = str(data.get("subject") or "").strip()
            # Only treat the subject as a brand when it looks like a single
            # product name — "Notion vs Obsidian for research teams" is a topic,
            # not something you can search for as a company.
            subject_ok = bool(subject) and len(subject) <= 40 and not any(
                k in subject.lower()
                for k in (" vs ", " versus ", "compar", "analysis", "research",
                          "landscape", " and ", "/", "market")
            )
            merged: List[str] = []
            for b in user_brands + ([subject] if subject_ok else []) + llm_brands:
                b = b.strip()
                if b and b not in merged:
                    merged.append(b)
            brands = merged[:6]
            angles = [
                a for a in data.get("search_angles", []) if isinstance(a, str)
            ][:max_angles]
            focus = [f for f in data.get("focus", []) if isinstance(f, str)]
            category = str(data.get("category") or "").strip()
            if brands:
                return {
                    "brands": brands,
                    "focus": focus or _DEFAULT_FOCUS,
                    "angles": angles or _DEFAULT_ANGLES,
                    "category": category,
                }
    except Exception:
        pass
    fallback_brands = user_brands or _regex_brands(query)
    return {
        "brands": fallback_brands[:6],
        "focus": list(_DEFAULT_FOCUS),
        "angles": list(_DEFAULT_ANGLES[:max_angles]),
        "category": str(clar.get("_category") or "").strip(),
    }


_DEFAULT_FOCUS = ["Product", "Pricing", "User sentiment"]
_DEFAULT_ANGLES = [
    "product features",
    "pricing plans",
    "user reviews",
    "latest news 2026",
    "market share",
]

# Words that appear in research requests but are never brand names.
_BRAND_STOPWORDS = {
    "analysis", "analyze", "compare", "comparison", "competitive", "competitor",
    "competitors", "research", "report", "market", "landscape", "versus", "vs",
    "pricing", "price", "product", "products", "features", "review", "reviews",
    "the", "and", "for", "with", "against", "between", "study", "deep", "dive",
    "top", "best", "vs.", "overview", "strategy",
    "of", "in", "on", "to", "at", "by", "from", "a", "an", "is", "are", "as",
    "how", "what", "why", "which", "who", "into", "about", "across", "their",
}


def _regex_brands(query: str) -> List[str]:
    """Last-resort brand extraction when the planning call fails."""
    tokens = re.split(r"[,;/\s]+", query)
    cand = []
    for t in tokens:
        clean = t.strip().strip(".,!?'\"")
        if not clean or clean.lower() in _BRAND_STOPWORDS:
            continue
        if len(clean) < 2 or len(clean) > 30 or clean.isdigit():
            continue
        cand.append(clean)
    return cand[:4] if cand else ["Target competitor"]


# ── Expert dispatch ───────────────────────────────────────────────────────────
def _dispatch_experts(query: str, brands: List[str], focus: List[str]) -> Dict[str, Any]:
    experts = load_experts()
    roster = [
        {
            "id": e["id"],
            "name": e["name"],
            "level": e["level"],
            "role": e["role_title"],
            "skills": e.get("skills", [])[:3],
        }
        for e in experts
    ]
    try:
        data = chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You are the commanding director of a competitive "
                        "research firm. Pick the right team for this engagement "
                        "from the roster.\n\n"
                        "Rules: exactly 1 L3 decision-tier lead, 1-2 L2 strategy "
                        "advisors, and 3-6 L1 specialists. Match specialists to "
                        "the actual subject matter — a fintech question needs the "
                        "financial services analyst, not the gaming one.\n"
                        "Give each pick a specific reason naming what they will "
                        "own and why they fit.\n"
                        'Return JSON: {"lead":"expert id",'
                        '"members":[{"id":"expert id","reason":"..."}]}'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Research topic: {query}\n"
                        f"Competitors: {', '.join(brands)}\n"
                        f"Focus areas: {', '.join(focus)}\n"
                        f"Roster: {json.dumps(roster)}"
                    ),
                },
            ],
            max_tokens=2000,
            temperature=0.4,
            model=_model("fast"),
            purpose="Assemble the expert team",
        )
        if isinstance(data, dict) and data.get("members"):
            valid_ids = {e["id"] for e in experts}
            members = [
                {"id": m["id"], "reason": m.get("reason", "")}
                for m in data["members"]
                if isinstance(m, dict) and m.get("id") in valid_ids
            ]
            lead = data.get("lead") if data.get("lead") in valid_ids else None
            if members:
                if not lead:
                    lead = members[0]["id"]
                return {"lead": lead, "members": members}
    except Exception:
        pass
    fallback = [
        {"id": "L3-001", "reason": "Directs the engagement and signs off"},
        {"id": "L2-001", "reason": "Reads the competitive structure"},
        {"id": "L2-002", "reason": "Breaks down pricing and packaging"},
        {"id": "L1-025", "reason": "Runs web collection and extraction"},
        {"id": "L1-030", "reason": "Handles social listening and sentiment"},
        {"id": "L3-003", "reason": "Enforces the four iron rules"},
    ]
    return {"lead": "L3-001", "members": fallback}


DAG_NODES = [
    {"id": "intake", "label": "Understand"},
    {"id": "orchestrator", "label": "Assemble"},
    {"id": "collect", "label": "Collect"},
    {"id": "analyze", "label": "Analyze"},
    {"id": "write", "label": "Write"},
    {"id": "audit", "label": "Review"},
    {"id": "done", "label": "Deliver"},
]


def _ev(type_: str, data: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": type_, "data": data}


# Domains that classify a URL into a source type.
_ANALYST_DOMAINS = (
    "gartner.com", "forrester.com", "idc.com", "cbinsights.com", "pitchbook.com",
    "crunchbase.com", "statista.com", "emarketer.com", "mckinsey.com",
    "bain.com", "bcg.com", "deloitte.com", "pwc.com",
)
_NEWS_DOMAINS = (
    "news", "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "cnbc.com",
    "nytimes.com", "washingtonpost.com", "apnews.com", "npr.org", "axios.com",
    "techcrunch.com", "theverge.com", "wired.com", "arstechnica.com",
    "venturebeat.com", "zdnet.com", "engadget.com", "businessinsider.com",
    "forbes.com", "fortune.com", "economist.com", "theinformation.com",
    "protocol.com", "semafor.com", "theregister.com",
)
_REVIEW_DOMAINS = (
    "g2.com", "capterra.com", "trustpilot.com", "trustradius.com",
    "softwareadvice.com", "getapp.com", "producthunt.com", "gartner.com/reviews",
)
_FORUM_DOMAINS = (
    "stackoverflow.com", "stackexchange.com", "quora.com", "discourse",
    "community.", "forum.", "forums.", "discuss.",
)
# Anything with these in the domain is a publication or platform, not a vendor site.
_NON_OFFICIAL_HINTS = (
    "blog", "news", "wiki", "medium", "substack", "wordpress", "blogspot",
    "github.io", "notion.site", "dev.to", "hashnode", "tumblr",
)


def _source_type(url: str) -> str:
    d = domain_of(url)
    full = d + url.lower()

    if "reddit.com" in d:
        return SourceType.REDDIT
    if "news.ycombinator.com" in d or "ycombinator.com" in d:
        return SourceType.HACKERNEWS
    if "youtube.com" in d or "youtu.be" in d:
        return SourceType.YOUTUBE
    if d in ("x.com", "twitter.com") or d.endswith(".twitter.com"):
        return SourceType.X
    if any(k in d for k in _REVIEW_DOMAINS):
        return SourceType.REVIEW
    if any(k in d for k in _FORUM_DOMAINS):
        return SourceType.FORUM
    # Filings and investor relations.
    if any(
        k in full
        for k in ("sec.gov", "/investor", "ir.", "investorrelations", "annualreport",
                  "10-k", "10-q", "8-k", "form-s-1", "edgar")
    ):
        return SourceType.SEC_FILING
    if any(k in d for k in _ANALYST_DOMAINS):
        return SourceType.ANALYST
    if any(k in d for k in _NEWS_DOMAINS):
        return SourceType.NEWS
    if not d:
        return SourceType.WEB
    if _looks_official(d):
        return SourceType.OFFICIAL
    return SourceType.WEB


def _looks_official(domain: str) -> bool:
    """Rough test for a vendor's own site: shallow domain, no publishing markers.

    Deliberately conservative — misclassifying a blog as `official` would inflate
    its credibility score, so anything ambiguous falls through to `web`.
    """
    if any(h in domain for h in _NON_OFFICIAL_HINTS):
        return False
    parts = [p for p in domain.split(".") if p]
    if len(parts) <= 3 and parts and len(parts[0]) <= 24:
        return True
    return False


def _category_keywords(category: str) -> List[str]:
    """Split a category phrase into keywords used for relevance disambiguation.

    This is what keeps a search for a product called "Arc" from returning
    welding equipment.
    """
    if not category:
        return []
    kws: List[str] = []
    for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{1,}", category.lower()):
        if w not in _BRAND_STOPWORDS and len(w) >= 3:
            kws.append(w)
    seen: set = set()
    return [k for k in kws if not (k in seen or seen.add(k))]


def _sentiment_relevant(
    brand: str, cat_keywords: List[str], title: str, text: str
) -> bool:
    """Keep a user-voice result only if it is plausibly about the right thing.

    Short brand names are the hard case: a product called "Arc" matches welding
    supply pages, and "Notion" matches philosophy essays. So a name hit alone
    only settles it for reasonably distinctive names — for short ones the
    category has to corroborate. Without the brand name at all, a category
    keyword is required either way.
    """
    blob = f"{title} {text}".lower()
    b = (brand or "").lower().strip()
    if not b:
        return True
    brand_hit = len(b) >= 2 and b in blob
    cat_hit = any(k in blob for k in cat_keywords) if cat_keywords else False

    if brand_hit:
        # An ambiguous short name needs the category to back it up.
        if cat_keywords and len(b) <= 5:
            return cat_hit
        return True
    return cat_hit


# ── Per-brand collection ──────────────────────────────────────────────────────
def _collect_brand(
    brand: str,
    angles: List[str],
    collector: str,
    fetch_limit: int,
    freshness: str,
    existing_urls: set,
    task_id: str = "",
) -> Dict[str, Any]:
    """Search, fetch and build Evidence for one brand.

    Synchronous so it can be handed to `asyncio.to_thread`. `existing_urls` is
    shared across rounds so rework collection does not re-ingest the same pages.
    """
    queries = [f"{brand} {a}" for a in angles]
    results = multi_search(queries, num=10, freshness=freshness, task_id=task_id)
    out_ev: List[Evidence] = []
    out_img: List[Dict[str, Any]] = []
    fetched = 0
    for r in results:
        if fetched >= fetch_limit:
            break
        url = r.get("url", "")
        if not url or url in existing_urls:
            continue
        # Exa and Tavily already return page text; that skips a round trip.
        page = fetch_page(
            url,
            fallback_snippet=r.get("snippet", ""),
            prefetched_text=r.get("content") or "",
        )
        ok = page.get("ok")
        text = (page.get("text") or r.get("snippet", "")).strip()
        if not text:
            continue
        if not is_relevant_content(text, [brand], brand):
            continue
        existing_urls.add(url)
        stype = _source_type(url)
        captured = page.get("captured_at", _now())
        pub_date = r.get("captured_at", "")
        cred = score_evidence(
            url,
            stype,
            captured_at=pub_date or captured,
            has_publish_date=bool(pub_date),
            ok_fetch=bool(ok),
            excerpt=text[:280],
        )
        ev = Evidence(
            evidence_id=_sid("e"),
            source_url=url,
            source_type=stype,
            title=r.get("title", brand),
            excerpt=text[:280],
            captured_at=pub_date or captured,
            credibility=cred,
            collected_by=collector,
            image_urls=[im["src"] for im in page.get("images", [])][:3],
            brand=brand,
            domain=domain_of(url),
            freshness_days=freshness_days(pub_date or captured),
        )
        ev._full_text = text[:1500]  # type: ignore[attr-defined]
        out_ev.append(ev)

        og = (page.get("og_image") or "").strip()
        pics = page.get("images", []) or []
        fig_src = og or (pics[0]["src"] if pics else "")
        if fig_src:
            out_img.append(
                {
                    "src": fig_src,
                    "alt": "" if og else (pics[0].get("alt", "") if pics else ""),
                    "title": r.get("title", brand),
                    "source_url": url,
                    "domain": domain_of(url),
                    "source_type": stype,
                    "brand": brand,
                    "evidence_id": ev.evidence_id,
                }
            )
        fetched += 1
    return {"evidences": out_ev, "images": out_img, "found": len(results)}


def _collect_brand_voices(
    brand: str,
    category: str,
    cat_keywords: List[str],
    take: int,
    freshness: str,
    seen_urls: set,
    collector: str,
    task_id: str = "",
) -> Dict[str, Any]:
    """Gather user voice for one brand across every registered platform.

    API platforms (Reddit, Hacker News) return real comment bodies with scores
    and reply counts. Everything else falls back to site-restricted search, and
    then to open-web search naming the platform when the site filter yields
    nothing. Returns comments plus the Evidence records backing them.
    """
    comments: List[Dict[str, Any]] = []
    evidences: List[Evidence] = []
    plat_counts: Counter = Counter()
    dropped = 0

    def _add(
        text: str, url: str, title: str, platform: str, stype: str,
        published: str = "", signals: Optional[dict] = None,
    ) -> None:
        nonlocal dropped
        if not url or not text or url in seen_urls:
            return
        if not _sentiment_relevant(brand, cat_keywords, title, text):
            dropped += 1
            return
        seen_urls.add(url)
        comments.append(
            {
                "text": text,
                "platform": platform,
                "url": url,
                "title": title,
                "brand": brand,
                "signals": signals or {},
            }
        )
        plat_counts[platform] += 1
        evidences.append(
            Evidence(
                evidence_id=_sid("e"),
                source_url=url,
                source_type=stype,
                title=title or f"{brand} user sentiment",
                excerpt=text[:280],
                captured_at=published or _now(),
                credibility=score_evidence(
                    url, stype, captured_at=published,
                    has_publish_date=bool(published), ok_fetch=False,
                    excerpt=text[:280], signals=signals or {},
                ),
                collected_by=collector,
                brand=brand,
                domain=domain_of(url),
                freshness_days=freshness_days(published),
            )
        )

    # 1. Real APIs.
    for plat in api_platforms():
        try:
            rows = plat.collector(brand, category, limit=take) or []
        except Exception:
            rows = []
        for row in rows:
            _add(
                text=row.get("text", ""),
                url=row.get("url", ""),
                title=row.get("title", ""),
                platform=plat.key,
                stype=plat.source_type,
                published=row.get("created_at", ""),
                signals=row.get("signals") or {},
            )
        if rows:
            trace.record_manual_span(
                task_id, collector, "collect",
                f"Collect {plat.label} discussion for \"{brand}\"",
                detail=f"{plat.label} API, query: {brand} {category}".strip(),
                decision=f"{len(rows)} items returned via API",
                model=f"— ({plat.label} API)",
            )

    # 2. Site-restricted search for platforms without an API.
    for plat in search_platforms():
        queries = plat.queries(brand, category)
        try:
            results = multi_search(
                queries, num=8, site=plat.domain, freshness=freshness, task_id=task_id
            )
        except Exception:
            results = []
        if not results:
            # Some providers filter site-restricted queries aggressively; retry
            # on the open web with the platform named in the query instead.
            fb = [f"{q} {plat.label}" for q in queries]
            try:
                results = multi_search(fb, num=8, freshness=freshness, task_id=task_id)
            except Exception:
                results = []
        for r in results[:take]:
            url = r.get("url", "")
            title = r.get("title", "")
            text = (r.get("snippet") or title or "").strip()
            detected = _source_type(url)
            # Trust the detected type when it is a recognizable platform;
            # otherwise attribute to the platform we were searching.
            platform = plat.key
            stype = plat.source_type
            if detected in SourceType.SOCIAL:
                stype = detected
                for k, v in PLATFORM_SOURCE_TYPE.items():
                    if v == detected:
                        platform = k
                        break
            _add(
                text=text, url=url, title=title, platform=platform,
                stype=stype, published=r.get("captured_at", ""),
            )

    return {
        "comments": comments,
        "evidences": evidences,
        "platform_counts": dict(plat_counts),
        "dropped": dropped,
    }


# ── Main pipeline ─────────────────────────────────────────────────────────────
async def run_pipeline(task_id: str, sub_id: str = "") -> AsyncIterator[Dict[str, Any]]:
    task = db.get_task(task_id) or {"query": "Competitive analysis", "clarifications": {}}
    query = task.get("query", "Competitive analysis")
    clar = task.get("clarifications", {}) or {}
    mode = clar.get("_mode", "deep")
    if mode not in MODE_CONFIG:
        mode = "deep"
    cfg = MODE_CONFIG[mode]
    perspective = _normalize_perspective(clar.get("perspective", ""))

    t_start = time.monotonic()
    token_start = TOKEN_USAGE["total"]
    progress = {"percent": 0, "evidence_count": 0, "token_used": 0, "stage": "intake"}

    def prog(percent: int, stage: str, ev_count: int, queued: int = 0) -> Dict[str, Any]:
        progress.update(
            {
                "percent": percent,
                "stage": stage,
                "evidence_count": ev_count,
                "token_used": TOKEN_USAGE["total"] - token_start,
                # Surfaced so a rate-limited run reads as "queued", not "hung".
                "queued": queued,
            }
        )
        return dict(progress)

    def _drain_trace():
        return [_ev("trace", sp) for sp in trace.drain(task_id)]

    yield _ev("node_update", {"nodes": [{**n, "status": "idle"} for n in DAG_NODES]})
    yield _ev(
        "message",
        {"id": _sid("m"), "kind": "mode", "text": f"{cfg['label']} research mode", "mode": mode},
    )
    await asyncio.sleep(0.15)

    # ---- 1. intake ----
    yield _ev("node_update", {"node": "intake", "status": "working", "expert": "L3-001"})
    yield _ev(
        "thought",
        {
            "id": _sid("th"), "kind": "plan", "expert": "L3-001",
            "text": f"Brief received: {query} ({cfg['label']} mode). Identifying "
                    "the competitive set and the dimensions that matter.",
            "ts": _now(),
        },
    )
    trace.set_context(task_id, "L3-001", "intake", "Break down the research brief")
    plan = await asyncio.to_thread(_plan_research, query, clar, cfg["max_angles"])
    for e in _drain_trace():
        yield e
    brands = plan["brands"]
    focus = plan["focus"]
    angles = plan["angles"]
    category = plan.get("category", "")
    yield _ev(
        "thought",
        {
            "id": _sid("th"), "kind": "plan", "expert": "L3-001",
            "text": f"Competitive set: {', '.join(brands)}. Focus: {', '.join(focus)}. "
                    f"Searching from {len(angles)} angles — {', '.join(angles[:4])}"
                    f"{'…' if len(angles) > 4 else ''}.",
            "ts": _now(),
        },
    )
    yield _ev("progress", prog(7, "intake", 0))
    yield _ev("node_update", {"node": "intake", "status": "done"})

    # ---- 2. orchestrator ----
    yield _ev("node_update", {"node": "orchestrator", "status": "working", "expert": "L3-001"})
    trace.set_context(task_id, "L3-001", "orchestrator", "Assemble the expert team")
    dispatch = await asyncio.to_thread(_dispatch_experts, query, brands, focus)
    for e in _drain_trace():
        yield e
    member_ids = [m["id"] for m in dispatch["members"]]
    lead_expert = expert_by_id(dispatch["lead"]) or {}
    yield _ev(
        "thought",
        {
            "id": _sid("th"), "kind": "dispatch", "expert": "L3-001",
            "text": f"{lead_expert.get('name','The director')} is leading a "
                    f"{len(member_ids)}-person team matched to this brief.",
            "ts": _now(),
        },
    )
    for m in dispatch["members"]:
        ex = expert_by_id(m["id"]) or {}
        yield _ev(
            "thought",
            {
                "id": _sid("th"), "kind": "dispatch", "expert": m["id"],
                "text": f"{ex.get('name', m['id'])} ({ex.get('role_title','')}): {m['reason']}",
                "ts": _now(),
            },
        )
        await asyncio.sleep(0.04)
    env_collect = Envelope(
        msg_id="env_" + uuid.uuid4().hex[:8], sender="L3-001", receiver="collect",
        task_type="PRODUCE", payload={"brands": brands, "angles": angles},
    )
    yield _ev(
        "message",
        {
            "id": _sid("m"), "kind": "team", "expert": "L3-001", "members": member_ids,
            "text": "Team is staffed. Beginning evidence collection.",
            "dispatch": dispatch["members"],
            "envelope": {
                "sender": env_collect.sender, "receiver": env_collect.receiver,
                "task_type": env_collect.task_type, "payload": env_collect.payload,
            },
        },
    )
    yield _ev("progress", prog(14, "orchestrator", 0))
    yield _ev("node_update", {"node": "orchestrator", "status": "done"})

    collector = next(
        (m["id"] for m in dispatch["members"] if m["id"].startswith("L1")), "L1-025"
    )
    sentiment_expert = next(
        (
            m["id"]
            for m in dispatch["members"]
            if (expert_by_id(m["id"]) or {}).get("group") == "function"
        ),
        collector,
    )

    # ---- 3. collect ----
    yield _ev("node_update", {"node": "collect", "status": "working", "expert": collector})
    evidences: List[Evidence] = []
    images: List[Dict[str, str]] = []
    ev_by_collector: Counter = Counter()
    collect_notes: List[str] = []
    seen_urls: set = set()

    for brand in brands:
        yield _ev(
            "thought",
            {
                "id": _sid("th"), "kind": "action", "expert": collector,
                "text": f"Searching for \"{brand}\" across {len(angles)} angles.",
                "ts": _now(),
            },
        )
        trace.set_context(task_id, collector, "collect", f"Collect evidence on \"{brand}\"")
        res = await asyncio.to_thread(
            _collect_brand, brand, angles, collector,
            cfg["fetch_per_brand"], cfg["freshness"], seen_urls, task_id,
        )
        for e in _drain_trace():
            yield e
        if not res["evidences"]:
            collect_notes.append(
                f"No usable sources were retrieved for \"{brand}\" — the search may "
                "have been rate-limited or the results were off-topic. Recorded as "
                "a gap rather than filled in."
            )
            trace.record_manual_span(
                task_id, collector, "collect", f"Collect evidence on \"{brand}\"",
                detail=f"Angles: {', '.join(angles)}\nFreshness: {cfg['freshness']}",
                decision=f"\"{brand}\" returned nothing usable; recorded as a gap.",
            )
            for e in _drain_trace():
                yield e
            yield _ev(
                "thought",
                {
                    "id": _sid("th"), "kind": "reflect", "expert": collector,
                    "text": f"\"{brand}\" returned nothing usable this round. Moving "
                            "on to the other competitors rather than stopping.",
                    "ts": _now(),
                },
            )
            continue
        yield _ev(
            "thought",
            {
                "id": _sid("th"), "kind": "finding", "expert": collector,
                "text": f"\"{brand}\": {res['found']} unique links found, "
                        f"{len(res['evidences'])} fetched and kept as evidence.",
                "ts": _now(),
            },
        )
        for ev in res["evidences"]:
            evidences.append(ev)
            ev_by_collector[collector] += 1
            d = ev.to_dict()
            d["domain"] = domain_of(ev.source_url)
            d["brand"] = ev.brand
            d["full_text"] = getattr(ev, "_full_text", "")
            yield _ev("evidence", {**d})
            yield _ev("progress", prog(min(14 + len(evidences), 50), "collect", len(evidences)))
            await asyncio.sleep(0.01)
        for fig in res["images"]:
            images.append(fig)
            yield _ev("image", fig)

        brand_domains = {domain_of(ev.source_url) for ev in res["evidences"]}
        brand_domains.discard("")
        trace.record_manual_span(
            task_id, collector, "collect", f"Collect evidence on \"{brand}\"",
            detail=f"Angles ({len(angles)}): {', '.join(angles)}\n"
                   f"Freshness filter: {cfg['freshness']}",
            decision=f"{res['found']} unique links -> {len(res['evidences'])} pieces of "
                     f"evidence across {len(brand_domains)} independent domains.",
            evidence_ids=[ev.evidence_id for ev in res["evidences"][:8]],
        )
        for e in _drain_trace():
            yield e

    # Social listening.
    yield _ev(
        "thought",
        {
            "id": _sid("th"), "kind": "action", "expert": sentiment_expert,
            "text": "Collecting user voice: Reddit and Hacker News through their "
                    "APIs, review sites and video through targeted search. Every "
                    "quote keeps its source link.",
            "ts": _now(),
        },
    )
    sentiment_comments: List[Dict[str, Any]] = []
    sentiment_brands = brands[: cfg.get("sentiment_brands", 3)]
    primary_brand = brands[0] if brands else ""
    take = cfg.get("platform_take", cfg.get("platform_per", 6))
    cat_kw = _category_keywords(category)

    for sb in sentiment_brands:
        trace.set_context(
            task_id, sentiment_expert, "collect", f"Collect user sentiment on \"{sb}\""
        )
        vres = await asyncio.to_thread(
            _collect_brand_voices, sb, category, cat_kw, take,
            cfg["freshness"], seen_urls, sentiment_expert, task_id,
        )
        for e in _drain_trace():
            yield e
        sentiment_comments.extend(vres["comments"])
        for ev in vres["evidences"]:
            evidences.append(ev)
            ev_by_collector[sentiment_expert] += 1
            d = ev.to_dict()
            d["domain"] = domain_of(ev.source_url)
            d["brand"] = sb
            yield _ev("evidence", {**d})
        yield _ev(
            "thought",
            {
                "id": _sid("th"), "kind": "finding", "expert": sentiment_expert,
                "text": f"\"{sb}\": {len(vres['comments'])} relevant comments kept "
                        f"({vres['dropped']} discarded as off-topic). "
                        f"By platform: {vres['platform_counts'] or 'none'}.",
                "ts": _now(),
            },
        )
    yield _ev(
        "thought",
        {
            "id": _sid("th"), "kind": "finding", "expert": sentiment_expert,
            "text": f"{len(sentiment_comments)} linked comments collected across "
                    f"{len(sentiment_brands)} brand(s).",
            "ts": _now(),
        },
    )

    yield _ev("node_update", {"node": "collect", "status": "done"})
    yield _ev("progress", prog(54, "analyze", len(evidences)))

    if not evidences:
        yield _ev(
            "error",
            {
                "message": "No usable evidence could be collected — both search and "
                           "page fetching failed. Check your search API key and "
                           "quota, then try again."
            },
        )
        return

    # ---- 4. analyze ----
    analyst = next(
        (m["id"] for m in dispatch["members"] if m["id"].startswith("L2")), "L2-001"
    )
    yield _ev("node_update", {"node": "analyze", "status": "working", "expert": analyst})
    yield _ev(
        "thought",
        {
            "id": _sid("th"), "kind": "action", "expert": analyst,
            "text": "Cross-validating the evidence: a conclusion needs two or more "
                    "independent domains before it can be called high confidence.",
            "ts": _now(),
        },
    )
    trace.set_context(task_id, analyst, "analyze", "Cross-validate and extract claims")
    analysis = await asyncio.to_thread(
        _analyze, query, brands, focus, evidences, member_ids, cfg["analyze_max_tokens"]
    )
    for e in _drain_trace():
        yield e
    claims = analysis["claims"]
    for cl in claims:
        yield _ev("message", {"id": _sid("m"), "kind": "claim", "claim": cl})
        await asyncio.sleep(0.03)

    yield _ev(
        "thought",
        {
            "id": _sid("th"), "kind": "action", "expert": analyst,
            "text": "Building the structured knowledge objects: feature tree, "
                    "pricing model and user personas, with citations enforced.",
            "ts": _now(),
        },
    )
    trace.set_context(task_id, analyst, "analyze", "Build structured competitive knowledge")
    structured = await asyncio.to_thread(
        _analyze_structured, query, brands, focus, evidences, cfg["structured_max_tokens"]
    )
    for e in _drain_trace():
        yield e
    analysis["structured"] = structured

    yield _ev(
        "thought",
        {
            "id": _sid("th"), "kind": "action", "expert": sentiment_expert,
            "text": "Classifying sentiment on the collected comments and clustering "
                    "them into opinion camps.",
            "ts": _now(),
        },
    )
    trace.set_context(task_id, sentiment_expert, "analyze", "Classify sentiment and cluster opinion")
    sentiment = await asyncio.to_thread(
        analyze_sentiment, primary_brand, sentiment_comments, _model("fast")
    )
    for e in _drain_trace():
        yield e
    yield _ev("progress", prog(64, "analyze", len(evidences)))
    yield _ev("node_update", {"node": "analyze", "status": "done"})

    # ---- 5. audit (runs before writing, so rework improves what gets written) ----
    auditor = next((m["id"] for m in dispatch["members"] if m["id"] == "L3-003"), "L3-003")
    yield _ev("node_update", {"node": "audit", "status": "working", "expert": auditor})
    yield _ev(
        "thought",
        {
            "id": _sid("th"), "kind": "reflect", "expert": auditor,
            "text": "Reviewing evidence coverage, dimension completeness and "
                    "confidence levels to decide whether this goes back for rework.",
            "ts": _now(),
        },
    )
    quality_before = evaluate_quality(brands, focus, claims, evidences, structured)
    trace.set_context(task_id, auditor, "audit", "Quality review: scores, issues, fixes")
    review_before = await asyncio.to_thread(
        llm_quality_review, query, brands, focus, claims, structured,
        quality_before, _model("aux"),
    )
    for e in _drain_trace():
        yield e
    yield _ev(
        "message",
        {
            "id": _sid("m"), "kind": "audit_review", "expert": auditor, "stage": "before",
            "verdict": review_before.get("verdict"),
            "scores": review_before.get("scores", {}),
            "review": review_before.get("review", ""),
            "issues": review_before.get("issues", []),
            "suggestions": review_before.get("suggestions", []),
        },
    )
    rework_rounds_done = 0
    issues_resolved = 0
    if cfg["rework_rounds"] > 0:
        envelopes = decide_rework(quality_before)
        # The rules can pass while the reviewer still objects. Synthesize an
        # analyze envelope so the reviewer's judgement can actually trigger the
        # loop rather than being advisory.
        if not envelopes and review_before.get("verdict") == "rework":
            envelopes = [
                Envelope(
                    msg_id="env_" + uuid.uuid4().hex[:8], sender="L3-003",
                    receiver="analyze", task_type="REWORK",
                    payload={"reason": "Reviewer requires stronger argument and cross-validation"},
                    issues=[
                        {"target": "review", "severity": "medium", "reason": r,
                         "raised_by": "L3-003"}
                        for r in review_before.get("issues", [])[:4]
                    ],
                )
            ]
        for _ in range(cfg["rework_rounds"]):
            if not envelopes:
                break
            for env in envelopes:
                if env.receiver == "collect":
                    recollect_brands = env.payload.get("brands", [])
                    yield _ev("node_update", {"node": "audit", "status": "rework"})
                    yield _ev("node_update", {"node": "collect", "status": "rework"})
                    yield _ev(
                        "message",
                        {
                            "id": _sid("m"), "kind": "rework", "expert": auditor,
                            "reason": "Evidence too thin — sending back to collection for: "
                                      f"{', '.join(recollect_brands) or 'affected brands'}",
                            "envelope": {
                                "sender": env.sender, "receiver": env.receiver,
                                "task_type": env.task_type, "issues": env.issues,
                            },
                        },
                    )
                    extra_angles = angles + [
                        "latest news 2026", "official announcement", "analyst report",
                    ]
                    for b in recollect_brands[:3]:
                        trace.set_context(task_id, collector, "collect", f"Rework: re-collect \"{b}\"")
                        res = await asyncio.to_thread(
                            _collect_brand, b, extra_angles[: cfg["max_angles"]],
                            collector, cfg["fetch_per_brand"], cfg["freshness"],
                            seen_urls, task_id,
                        )
                        for e in _drain_trace():
                            yield e
                        for ev in res["evidences"]:
                            evidences.append(ev)
                            ev_by_collector[collector] += 1
                            d = ev.to_dict()
                            d["domain"] = domain_of(ev.source_url)
                            d["brand"] = ev.brand
                            d["full_text"] = getattr(ev, "_full_text", "")
                            yield _ev("evidence", {**d})
                        for fig in res["images"]:
                            images.append(fig)
                            yield _ev("image", fig)
                    yield _ev("node_update", {"node": "collect", "status": "done"})
                elif env.receiver == "analyze":
                    yield _ev("node_update", {"node": "audit", "status": "rework"})
                    yield _ev("node_update", {"node": "analyze", "status": "rework"})
                    yield _ev(
                        "message",
                        {
                            "id": _sid("m"), "kind": "rework", "expert": auditor,
                            "reason": "Dimension or structural coverage incomplete — re-analyzing.",
                            "envelope": {
                                "sender": env.sender, "receiver": env.receiver,
                                "task_type": env.task_type, "issues": env.issues,
                            },
                        },
                    )
                    trace.set_context(
                        task_id, analyst, "analyze",
                        "Rework: address reviewer findings and strengthen cross-validation",
                    )
                    rework_fb = "\n".join(
                        f"- Problem: {x}" for x in review_before.get("issues", [])[:5]
                    )
                    if review_before.get("suggestions"):
                        rework_fb += "\n" + "\n".join(
                            f"- Suggestion: {x}"
                            for x in review_before.get("suggestions", [])[:5]
                        )
                    analysis = await asyncio.to_thread(
                        _analyze, query, brands, focus, evidences, member_ids,
                        cfg["analyze_max_tokens"], rework_fb,
                    )
                    for e in _drain_trace():
                        yield e
                    claims = analysis["claims"]
                    structured = await asyncio.to_thread(
                        _analyze_structured, query, brands, focus, evidences,
                        cfg["structured_max_tokens"],
                    )
                    analysis["structured"] = structured
                    yield _ev("node_update", {"node": "analyze", "status": "done"})
            rework_rounds_done += 1
            quality_after_round = evaluate_quality(
                brands, focus, claims, evidences, structured
            )
            issues_resolved = max(
                0, len(quality_before.issues) - len(quality_after_round.issues)
            )
            envelopes = decide_rework(quality_after_round)
        quality_after = evaluate_quality(brands, focus, claims, evidences, structured)
    else:
        quality_after = quality_before

    review_after = review_before
    if rework_rounds_done > 0:
        trace.set_context(task_id, auditor, "audit", "Re-review after rework")
        review_after = await asyncio.to_thread(
            llm_quality_review, query, brands, focus, claims, structured,
            quality_after, _model("aux"),
        )
        for e in _drain_trace():
            yield e
        # The reviewer regenerates its issue list each round, so raw issue counts
        # are noisy. The number of dimensions whose score improved is the more
        # reliable signal; take the strongest of the three.
        review_issues_resolved = max(
            0, len(review_before.get("issues", [])) - len(review_after.get("issues", []))
        )
        sc_b = review_before.get("scores", {}) or {}
        sc_a = review_after.get("scores", {}) or {}
        improved_dims = sum(1 for k in sc_a if k in sc_b and sc_a[k] > sc_b[k])
        issues_resolved = max(issues_resolved, review_issues_resolved, improved_dims)
        yield _ev(
            "message",
            {
                "id": _sid("m"), "kind": "audit_review", "expert": auditor, "stage": "after",
                "verdict": review_after.get("verdict"),
                "scores": review_after.get("scores", {}),
                "review": review_after.get("review", ""),
                "issues": review_after.get("issues", []),
                "suggestions": review_after.get("suggestions", []),
            },
        )
        yield _ev(
            "message",
            {
                "id": _sid("m"), "kind": "rework_result", "expert": auditor,
                "reason": "Rework complete — coverage and confidence improved.",
                "metrics_before": quality_before.summary(),
                "metrics_after": quality_after.summary(),
                "issues_resolved": issues_resolved,
            },
        )
    yield _ev("node_update", {"node": "audit", "status": "done"})
    yield _ev("progress", prog(70, "audit", len(evidences)))

    # ---- 6. write ----
    writer = next(
        (m["id"] for m in dispatch["members"] if m["id"] == "L3-002"), dispatch["lead"]
    )
    yield _ev("node_update", {"node": "write", "status": "working", "expert": writer})
    section_ids = list(cfg["sections"])
    persp_sid = PERSPECTIVE_SECTION.get(perspective)
    if persp_sid and persp_sid not in section_ids:
        insert_pos = (
            section_ids.index("conclusion")
            if "conclusion" in section_ids
            else len(section_ids)
        )
        section_ids.insert(insert_pos, persp_sid)
    yield _ev(
        "thought",
        {
            "id": _sid("th"), "kind": "plan", "expert": writer,
            "text": f"Writing {len(section_ids)} sections in parallel on "
                    f"{_model('core')}. Requests are paced to stay inside the "
                    "model's rate limit, so sections land progressively.",
            "ts": _now(),
        },
    )

    sections_text: Dict[str, Dict[str, Any]] = {}

    async def _write_one(sid: str):
        title = dict(SECTION_PLAN).get(sid, sid)
        model = _model("core") if sid in CORE_SECTIONS else _model("aux")
        trace.set_context(task_id, writer, "write", f"Write section: {title}")
        return sid, await asyncio.to_thread(
            _write_single_section, sid, title, query, brands, focus,
            evidences, claims, analysis, model,
            cfg["min_paragraphs"], cfg["para_words"], cfg["section_max_tokens"],
        )

    tasks = [asyncio.create_task(_write_one(sid)) for sid in section_ids]
    done_count = 0
    total = len(tasks)
    for coro in asyncio.as_completed(tasks):
        sid, st = await coro
        sections_text[sid] = st
        done_count += 1
        for e in _drain_trace():
            yield e
        title = dict(SECTION_PLAN).get(sid, sid)
        yield _ev(
            "thought",
            {
                "id": _sid("th"), "kind": "finding", "expert": writer,
                "text": f"Section {done_count}/{total} complete: {title}.",
                "ts": _now(),
            },
        )
        yield _ev(
            "progress",
            prog(70 + int(16 * done_count / total), "write", len(evidences),
                 queued=total - done_count),
        )

    sentiment_text: Dict[str, Any] = {"paragraphs": [], "key_takeaway": "", "highlights": []}
    if sentiment.get("sample_size"):
        trace.set_context(task_id, sentiment_expert, "write", "Write section: User sentiment")
        sentiment_text = await asyncio.to_thread(
            _write_sentiment_narrative, query, brands, sentiment, _model("aux"),
            cfg["min_paragraphs"], cfg["para_words"], cfg["section_max_tokens"],
        )
        for e in _drain_trace():
            yield e

    chart_specs = _build_charts(brands, analysis, sentiment, claims)
    for ch in chart_specs:
        yield _ev("chart", ch)
        await asyncio.sleep(0.05)
    yield _ev("progress", prog(90, "write", len(evidences)))
    yield _ev("node_update", {"node": "write", "status": "done"})

    # ---- 7. done ----
    yield _ev("node_update", {"node": "done", "status": "working", "expert": dispatch["lead"]})
    yield _ev("progress", prog(95, "done", len(evidences)))

    elapsed = time.monotonic() - t_start
    tokens_used = TOKEN_USAGE["total"] - token_start
    metrics = compute_report_metrics(
        brands=brands, focus=focus, claims=claims, evidences=evidences,
        structured=structured, elapsed_seconds=elapsed, tokens_used=tokens_used,
        rework_rounds=rework_rounds_done, issues_resolved=issues_resolved,
    )
    metrics = merge_quality_into_metrics(metrics, quality_after.to_dict())

    trace_spans = trace.get_trace(task_id)
    report = _assemble_report(
        query, brands, focus, dispatch, claims, evidences, images, sentiment,
        chart_specs, sections_text, collect_notes, analysis, metrics,
        quality_before.to_dict(), quality_after.to_dict(), trace_spans, mode,
        section_ids, sentiment_text,
    )
    report["audit_review"] = {
        "before": review_before, "after": review_after,
        "rework_rounds": rework_rounds_done, "issues_resolved": issues_resolved,
    }
    db.save_report(report, task_id=task_id)
    db.save_traces(task_id, report["id"], trace_spans)
    db.mark_task_done(task_id, report["id"])
    claims_by_author = Counter(c.get("author", "") for c in claims if c.get("author"))
    db.bump_expert_stats(member_ids, dict(claims_by_author), dict(ev_by_collector))
    if sub_id:
        db.mark_subscription_run(sub_id, report["id"])
    trace.cleanup(task_id)

    yield _ev("progress", prog(100, "done", len(evidences)))
    yield _ev("node_update", {"node": "done", "status": "done"})
    yield _ev(
        "report_ready",
        {"reportId": report["id"], "title": report["title"],
         "cover_image": report["cover_image"]},
    )
    yield _ev("done", {"reportId": report["id"]})


# ── Analysis ──────────────────────────────────────────────────────────────────
def _evidence_digest(evidences: List[Evidence], limit: int = 28) -> str:
    return "\n".join(
        f"[{e.evidence_id}|{e.source_type}|{domain_of(e.source_url)}] {e.title}: {e.excerpt}"
        for e in evidences[:limit]
    )


def _analyze(
    query, brands, focus, evidences: List[Evidence], members: List[str],
    max_tokens_param: int = 8000, review_feedback: str = "",
) -> Dict[str, Any]:
    digest = _evidence_digest(evidences)
    ev_ids = [e.evidence_id for e in evidences]
    domains_by_id = {e.evidence_id: domain_of(e.source_url) for e in evidences}
    authors = [m for m in members if m.startswith(("L1", "L2"))] or ["L2-001"]

    rework_directive = ""
    if review_feedback:
        rework_directive = (
            "\n\n[REWORK REQUIRED — address each point specifically]\n"
            + review_feedback
            + "\n\nAct on this: (1) for any low-confidence or single-sourced "
            "conclusion, find a second independent source before restating it, "
            "raising the share of high-confidence claims; (2) fill the dimensions "
            "flagged as missing so every focus area has at least one evidenced "
            "conclusion; (3) make the conclusions sharper and more differentiated."
        )

    fallback = {
        "claims": _fallback_claims(brands, ev_ids, domains_by_id, authors),
        "comparison": {
            "dimensions": ["Feature depth", "Ease of use", "Value", "Ecosystem", "Support"],
            "scores": [{"brand": b, "values": []} for b in brands[:4]],
        },
        "pricing": [{"brand": b, "entry_price": None} for b in brands[:4]],
        "market_share": [],
        "five_forces": {},
        "trends": {},
    }
    try:
        data = chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a senior competitive analyst writing at the level "
                        "of top-tier equity research or an MBB strategy engagement. "
                        "From the evidence provided — each item carries an "
                        "evidence_id — extract structured competitive insight that "
                        "takes a position.\n\n"
                        "Hard requirements:\n"
                        "* every claim's evidence_ids must be real ids from the "
                        "evidence below; a claim you cannot source, you do not make;\n"
                        "* prefer specific figures over adjectives, and say where "
                        "each figure came from;\n"
                        "* state a judgement, not a summary. 'Both tools are strong "
                        "in their own way' is not analysis.\n\n"
                        "Return JSON: {"
                        '"claims":[{"text":"one sharp, falsifiable conclusion",'
                        '"field":"overview|feature_tree|pricing_model|user_persona|swot|trend",'
                        '"evidence_ids":["real id"],"author":"expert id"}],'
                        '"comparison":{"dimensions":["5-6 capability dimensions"],'
                        '"scores":[{"brand":"...","values":[integers 0-100, same length as dimensions]}]},'
                        '"pricing":[{"brand":"...","entry_price":number or null,"note":"pricing model and what it signals"}],'
                        '"market_share":[{"name":"...","value":integer percent}],'
                        '"five_forces":{"rivalry":0-100,"new_entrants":0-100,"substitutes":0-100,'
                        '"buyer_power":0-100,"supplier_power":0-100,"note":"one-line read"},'
                        '"trends":{"x":["time points"],"unit":"metric unit","series":[{"name":"...","values":[numbers matching x]}],"note":"one-line read"}}\n\n'
                        "five_forces quantifies competitive pressure per direction "
                        "(higher = more pressure), grounded in the evidence.\n"
                        "trends needs a comparable time series the evidence can "
                        "actually support — release cadence, user counts, revenue "
                        "growth. If nothing supports one, return {} rather than "
                        "inventing a series.\n"
                        "comparison, pricing and market_share must follow from the "
                        "evidence; leave them empty or null when it does not.\n\n"
                        "SCORING DISCIPLINE: scores must be precise and "
                        "differentiated. Do not return round multiples of five or "
                        "ten across the board — use values like 83, 77, 91, 68, and "
                        "make different brands and dimensions genuinely differ. "
                        "market_share values must sum to 100 or less; no percentage "
                        "may exceed 100."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Research topic: {query}\n"
                        f"Competitors: {', '.join(brands)}\n"
                        f"Focus: {', '.join(focus)}\n"
                        f"Valid author expert ids: {authors}\n"
                        f"Evidence:\n{digest}{rework_directive}"
                    ),
                },
            ],
            max_tokens=max_tokens_param,
            temperature=0.4,
            model=_model("core"),
            purpose="Cross-validate evidence into claims and comparison data",
        )
        if isinstance(data, dict) and data.get("claims"):
            claims = []
            valid_ids = set(ev_ids)
            for c in data["claims"]:
                if not isinstance(c, dict) or not c.get("text"):
                    continue
                eids = [i for i in c.get("evidence_ids", []) if i in valid_ids]
                indep = len({domains_by_id.get(i, "") for i in eids if domains_by_id.get(i)})
                author = c.get("author") if c.get("author") in members else authors[0]
                claims.append(
                    make_claim(
                        _sid("c"), c["text"], c.get("field", "overview"),
                        eids, author, indep,
                    ).to_dict()
                )
            if claims:
                return {
                    "claims": claims,
                    "comparison": data.get("comparison") or fallback["comparison"],
                    "pricing": data.get("pricing") or [],
                    "market_share": _sanitize_share(data.get("market_share") or []),
                    "five_forces": data.get("five_forces")
                    if isinstance(data.get("five_forces"), dict)
                    else {},
                    "trends": data.get("trends")
                    if isinstance(data.get("trends"), dict)
                    else {},
                }
    except Exception:
        pass
    return fallback


def _analyze_structured(
    query, brands, focus, evidences: List[Evidence], max_tokens_param: int = 8000
) -> Dict[str, Any]:
    """Feature tree, pricing model and personas under a strict schema."""
    digest = _evidence_digest(evidences, limit=24)
    valid_eids = {e.evidence_id for e in evidences}
    out = {"feature_tree": [], "pricing_model": [], "user_persona": []}
    try:
        data = chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You structure competitive knowledge. From the evidence "
                        "below — each item carries an evidence_id — produce strict "
                        "JSON for every competitor. Fields must be complete and "
                        "consistently formatted. evidence_ids must be real ids from "
                        "the evidence; use an empty array when you have none.\n\n"
                        "Return JSON: {"
                        '"feature_tree":[{"brand":"...","modules":[{"category":"...","name":"...",'
                        '"sub_features":[{"name":"...","support":"full|partial|none","note":"...","evidence_ids":["id"]}]}]}],'
                        '"pricing_model":[{"brand":"...","currency":"USD","model_type":"subscription|usage|freemium|one_time|free|custom",'
                        '"free_tier":true/false,"tiers":[{"name":"...","price":number or null,"period":"month|year",'
                        '"unit":"per user|per seat|flat","target_user":"...","includes":["..."],"evidence_ids":["id"]}]}],'
                        '"user_persona":[{"brand":"...","personas":[{"name":"...","segment":"...","needs":["..."],'
                        '"scenarios":["..."],"pain_points":["..."],"decision_factors":["..."],'
                        '"migration_cost":"...","evidence_ids":["id"]}]}]}'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Research topic: {query}\n"
                        f"Competitors: {', '.join(brands)}\n"
                        f"Focus: {', '.join(focus)}\n"
                        f"Evidence:\n{digest}"
                    ),
                },
            ],
            max_tokens=max_tokens_param,
            temperature=0.3,
            model=_model("core"),
            purpose="Structured competitive knowledge (features / pricing / personas)",
        )
        if isinstance(data, dict):
            out["feature_tree"] = coerce_feature_tree(data, valid_eids)
            out["pricing_model"] = coerce_pricing_model(data, valid_eids)
            out["user_persona"] = coerce_user_persona(data, valid_eids)
    except Exception:
        pass
    return out


def _sanitize_share(share: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Guard against impossible market shares by renormalizing anything over 100."""
    clean = [
        s
        for s in share
        if isinstance(s, dict)
        and isinstance(s.get("value"), (int, float))
        and s["value"] > 0
    ]
    total = sum(s["value"] for s in clean)
    if total > 100 and total > 0:
        for s in clean:
            s["value"] = round(s["value"] / total * 100, 1)
    return clean


def _fallback_claims(brands, ev_ids, domains_by_id, authors) -> List[Dict[str, Any]]:
    """With no model available, state only what the evidence set itself supports."""
    indep = len({domains_by_id.get(i, "") for i in ev_ids[:3] if domains_by_id.get(i)})
    return [
        make_claim(
            _sid("c"),
            f"Public evidence was collected for {', '.join(brands)}; every "
            "conclusion below carries its source for verification.",
            "overview", ev_ids[:3], authors[0], indep,
        ).to_dict()
    ]


# ── Section catalogue ─────────────────────────────────────────────────────────
SECTION_PLAN = [
    ("summary", "Executive Summary"),
    ("overview", "1. Competitive Landscape"),
    ("feature", "2. Feature Matrix and Strategic Intent"),
    ("pricing", "3. Business Model and Pricing Dynamics"),
    ("persona", "4. Target Users and Use Cases"),
    ("trend", "5. Trajectory and Outlook"),
    ("swot", "6. SWOT and Strategic Options"),
    ("moat", "Moat Depth and Barriers to Entry"),
    ("inflection", "Inflection Points and Key Variables"),
    ("contrarian", "Contrarian Read"),
    ("conclusion", "Conclusions and Recommended Actions"),
    ("risk", "Risks and Uncertainties"),
    ("persp_pm", "Product Perspective: Roadmap Implications"),
    ("persp_ops", "Growth Perspective: Acquisition and Retention Plays"),
    ("persp_sales", "Sales Perspective: Battlecards and Objection Handling"),
    ("persp_user", "Buyer Perspective: How to Choose and What to Avoid"),
    ("persp_investor", "Investor Perspective: Moat, Growth and Value"),
]

PERSPECTIVE_SECTION = {
    "pm": "persp_pm",
    "ops": "persp_ops",
    "sales": "persp_sales",
    "user": "persp_user",
    "investor": "persp_investor",
}


def _normalize_perspective(raw: str) -> str:
    """Map the questionnaire answer to an internal perspective key."""
    s = (raw or "").lower()
    if "product" in s or s.strip() == "pm":
        return "pm"
    if "growth" in s or "marketing" in s or "ops" in s:
        return "ops"
    if "sales" in s:
        return "sales"
    if "investor" in s:
        return "investor"
    if "buyer" in s or "end user" in s or "consumer" in s:
        return "user"
    return ""  # general — no dedicated section


# Sections where quality matters most get the core model.
CORE_SECTIONS = {"summary", "feature", "pricing", "conclusion", "contrarian", "moat"}

SECTION_PROMPTS = {
    "summary": (
        "The executive summary. Give the 3-4 conclusions that matter most, "
        "answer-first, so a reader gets the whole picture in thirty seconds."
    ),
    "overview": (
        "Deconstruct the market using structure-conduct-performance and Porter's "
        "five forces: how concentrated is it, how intense is the rivalry, how are "
        "the players behaving, and what results is that producing."
    ),
    "feature": (
        "Decode the strategy behind the feature matrix. Do not list features — "
        "explain why each competitor built what they built, what they chose not "
        "to build, and where that creates defensibility or exposure."
    ),
    "pricing": (
        "Business model and pricing dynamics: each player's pricing strategy, "
        "revenue mix, unit economics, and where they draw the free-to-paid line "
        "and why."
    ),
    "persona": (
        "Target users and real usage scenarios: who each product is actually for, "
        "how they decide, and what switching would cost them."
    ),
    "trend": (
        "Trajectory and outlook. From release history and current signals, project "
        "the next one to two years and name the variables that would change it."
    ),
    "swot": (
        "SWOT for each player, then the strategic options that follow. Be specific "
        "enough that someone could act on it."
    ),
    "moat": (
        "Break down each player's moat across network effects, switching costs, "
        "scale economics, brand and data advantage. Assess how deep each really is, "
        "and name the weakest link."
    ),
    "inflection": (
        "The inflection points: the turns that shaped this market historically, and "
        "the variables and trigger conditions that could reshape it next."
    ),
    "contrarian": (
        "Two or three judgements that run against the consensus but are supported "
        "by the evidence. Say plainly why you think most observers have this wrong."
    ),
    "conclusion": (
        "Clear recommended actions for a decision-maker, ranked high/medium/low "
        "priority. Concrete moves, not generalities."
    ),
    "risk": (
        "Risk disclosure in the style of a research note: under what conditions "
        "these conclusions would fail, and what remains unknown."
    ),
    "persp_pm": (
        "For a product manager: each competitor's product philosophy and trade-offs, "
        "what is worth borrowing and what to avoid, where the feature gaps and "
        "differentiation openings are, and what that means for roadmap priority."
    ),
    "persp_ops": (
        "For growth and marketing: each competitor's acquisition, activation, "
        "retention and referral mechanics, their content and community strategy, "
        "and a list of plays that could be adopted immediately."
    ),
    "persp_sales": (
        "For sales: differentiated value propositions per competitor, head-to-head "
        "talk tracks, responses to the objections that actually come up, and one "
        "decisive line per matchup. Write it so a rep can use it in a live call."
    ),
    "persp_user": (
        "For a buyer: who each product suits best, the genuine strengths and the "
        "real pitfalls, total cost and switching cost, and a clear decision guide."
    ),
    "persp_investor": (
        "For an investor: market size and growth, the strength of each moat, "
        "business model health and unit economics, key risks, and the signals worth "
        "watching."
    ),
}


def _write_single_section(
    sid: str, title: str, query, brands, focus, evidences, claims, analysis,
    model: str, min_paragraphs: int = 5, para_words: str = "130-200",
    section_max_tokens: int = 6000,
) -> Dict[str, Any]:
    """Write one section. Independent token budget, so a failure is isolated."""
    field_map = {
        "summary": ["overview", "feature_tree", "pricing_model"],
        "overview": ["overview"],
        "feature": ["feature_tree"],
        "pricing": ["pricing_model"],
        "persona": ["user_persona"],
        "trend": ["trend"],
        "swot": ["swot"],
        "moat": ["overview", "feature_tree", "swot"],
        "inflection": ["trend", "overview"],
        "contrarian": ["overview", "swot", "trend"],
        "conclusion": ["overview", "feature_tree", "pricing_model", "swot"],
        "risk": ["overview", "trend", "swot"],
        "persp_pm": ["feature_tree", "overview", "trend"],
        "persp_ops": ["overview", "trend", "user_persona"],
        "persp_sales": ["feature_tree", "pricing_model", "swot"],
        "persp_user": ["user_persona", "feature_tree", "pricing_model"],
        "persp_investor": ["overview", "trend", "swot"],
    }
    fields = field_map.get(sid, ["overview"])
    rel_claims = [c for c in claims if c.get("field") in fields]
    digest = _evidence_digest(evidences, limit=20)
    claim_text = (
        "\n".join(
            f"- [{','.join(c.get('evidence_ids', [])) or 'no source'}] "
            f"{c['text']} ({c['confidence']})"
            for c in rel_claims[:8]
        )
        or "(no directly related claims — derive your own from the evidence)"
    )

    extra = ""
    ff = analysis.get("five_forces") or {}
    if ff.get("note") and sid in ("summary", "overview", "moat"):
        extra += f"\nFive-forces read: {ff['note']}"
    tr = analysis.get("trends") or {}
    if tr.get("note") and sid in ("summary", "trend", "inflection"):
        extra += f"\nTrend read: {tr['note']}"
    comp = analysis.get("comparison") or {}
    if comp.get("dimensions") and sid in ("summary", "feature", "moat"):
        extra += f"\nCapability dimensions: {', '.join(comp['dimensions'][:6])}"
    pricing = analysis.get("pricing") or []
    if pricing and sid in ("summary", "pricing"):
        extra += f"\nPricing data: {json.dumps(pricing[:3])}"
    structured = analysis.get("structured") or {}
    if sid == "feature" and structured.get("feature_tree"):
        extra += f"\nFeature tree: {json.dumps(structured['feature_tree'][:2])[:800]}"
    if sid == "pricing" and structured.get("pricing_model"):
        extra += f"\nPricing model: {json.dumps(structured['pricing_model'][:3])[:800]}"
    if sid == "persona" and structured.get("user_persona"):
        extra += f"\nPersonas: {json.dumps(structured['user_persona'][:2])[:800]}"

    section_role = SECTION_PROMPTS.get(sid, "An in-depth competitive analysis section.")
    try:
        data = chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You write competitive analysis at the level of a top "
                        "equity research note or an MBB strategy deliverable — "
                        "opinionated, evidence-led, willing to reach a verdict.\n\n"
                        f"This section: {section_role}\n\n"
                        "Requirements:\n"
                        "1. Answer first — open with the single sharpest judgement "
                        "as `key_takeaway`. It may be contrarian if the evidence "
                        "supports it.\n"
                        "2. Explain why, not what. Surface each competitor's "
                        "strategic intent and trade-offs, and reach your own "
                        "conclusion. Never write a sentence that would be true of "
                        "any company in any market.\n"
                        "3. Use the specific numbers, dates and facts in the "
                        "evidence. Where you have no data, say so rather than "
                        "reaching for a generality.\n"
                        f"4. At least {min_paragraphs} paragraphs of roughly "
                        f"{para_words} words each, building an argument — "
                        "observation, then mechanism, then implication, then "
                        "judgement. Do not write parallel lists of independent "
                        "points.\n"
                        "5. Give 2-3 `highlights`: the most striking findings, "
                        "contrasts or non-obvious insights, one sentence each.\n"
                        "6. Cite as you go. After a key conclusion, mark the "
                        "supporting evidence id in square brackets like [e_xxxx], "
                        "using only real ids from the material below.\n\n"
                        'Return JSON: {"paragraphs":["..."],'
                        '"key_takeaway":"...","highlights":["..."]}'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Section: {title}\n"
                        f"Research topic: {query}\n"
                        f"Competitors: {', '.join(brands)}\n"
                        f"Focus: {', '.join(focus)}\n"
                        f"Related claims (with supporting evidence ids):\n{claim_text}\n{extra}\n\n"
                        f"Evidence:\n{digest}"
                    ),
                },
            ],
            max_tokens=section_max_tokens,
            temperature=0.7,
            model=model,
            purpose=f"Write section: {title}",
        )
        if isinstance(data, dict):
            paras = data.get("paragraphs")
            if isinstance(paras, str):
                paras = [paras]
            paras = [
                str(p).strip() for p in (paras or [])
                if isinstance(p, str) and str(p).strip()
            ]
            hl = data.get("highlights")
            hl = (
                [str(h).strip() for h in hl if isinstance(h, str) and str(h).strip()]
                if isinstance(hl, list)
                else []
            )
            kt = str(data.get("key_takeaway", "")).strip()
            if paras:
                return {"paragraphs": paras, "key_takeaway": kt, "highlights": hl}
    except Exception:
        pass

    # One retry with a plainer prompt before giving up on the section.
    try:
        retry = chat(
            [
                {
                    "role": "system",
                    "content": (
                        f"You are a senior competitive analyst. Write at least "
                        f"{min_paragraphs} paragraphs of roughly {para_words} words "
                        "each for the section below, building a connected argument. "
                        "Output prose only — no JSON, no heading."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Section: {title}\nTopic: {query}\n"
                        f"Competitors: {', '.join(brands)}\n"
                        f"Evidence:\n{digest[:2000]}"
                    ),
                },
            ],
            max_tokens=section_max_tokens,
            temperature=0.7,
            model=model,
            purpose=f"Retry writing section: {title}",
        )
        paras = [p.strip() for p in retry.split("\n") if len(p.strip()) > 30]
        if paras:
            return {"paragraphs": paras, "key_takeaway": "", "highlights": []}
    except Exception:
        pass
    return {
        "paragraphs": [
            "This section could not be generated. Re-run the research or check "
            "the model's rate limit and daily quota."
        ],
        "key_takeaway": "",
        "highlights": [],
    }


def _write_sentiment_narrative(
    query, brands, sentiment: Dict[str, Any], model: str,
    min_paragraphs: int = 5, para_words: str = "130-200",
    section_max_tokens: int = 6000,
) -> Dict[str, Any]:
    """Interpret the sentiment data. Returns empty paragraphs when there is no data."""
    sample = sentiment.get("sample_size", 0)
    if not sample:
        return {"paragraphs": [], "key_takeaway": "", "highlights": []}

    overall = sentiment.get("overall", {})
    by_platform = sentiment.get("by_platform", {})
    camps = sentiment.get("camps", [])
    voices = sentiment.get("voices", [])
    plat_lines = (
        "; ".join(
            f"{PLATFORM_LABEL.get(p, p)}: {v.get('pos',0)} positive / "
            f"{v.get('neu',0)} neutral / {v.get('neg',0)} negative"
            for p, v in by_platform.items()
        )
        or "(no platform breakdown)"
    )
    camp_lines = (
        "\n".join(
            f"- {c.get('title','')} ({c.get('ratio',0)}%): {c.get('summary','')}"
            for c in camps
        )
        or "(no clear split)"
    )
    voice_lines = (
        "\n".join(
            f"- [{v.get('platform_label','')}|{v.get('sentiment','')}] {v.get('text','')}"
            for v in voices[:12]
        )
        or "(no representative quotes)"
    )

    try:
        data = chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a social-listening analyst and brand strategist. "
                        "Interpret the real sentiment data below.\n\n"
                        "Rules:\n"
                        "1. Work only from the data and quotes given. Never invent "
                        "a number, platform or comment.\n"
                        f"2. At least {min_paragraphs} paragraphs of roughly "
                        f"{para_words} words, progressing: overall picture -> "
                        "differences between platforms -> the opinion split -> what "
                        "the actual quotes show -> what it means for the brand.\n"
                        "3. Explain why the platforms differ — audience "
                        "composition, product positioning, who self-selects into "
                        "each community.\n"
                        "4. Give 2-3 `highlights`, one sentence each.\n"
                        "5. If the sample is small, say so plainly and mark the "
                        "read as directional. Do not paper over it.\n\n"
                        'Return JSON: {"paragraphs":["..."],'
                        '"key_takeaway":"...","highlights":["..."]}'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Research topic: {query}\n"
                        f"Competitors: {', '.join(brands)}\n"
                        f"Sample: {sample} linked comments\n"
                        f"Overall: {overall.get('pos',0)}% positive / "
                        f"{overall.get('neu',0)}% neutral / {overall.get('neg',0)}% negative\n"
                        f"By platform: {plat_lines}\n"
                        f"Opinion camps:\n{camp_lines}\n"
                        f"Representative quotes:\n{voice_lines}"
                    ),
                },
            ],
            max_tokens=section_max_tokens,
            temperature=0.6,
            model=model,
            purpose="Write section: user sentiment and opinion camps",
        )
        if isinstance(data, dict):
            paras = data.get("paragraphs")
            if isinstance(paras, str):
                paras = [paras]
            paras = [
                str(p).strip() for p in (paras or [])
                if isinstance(p, str) and str(p).strip()
            ]
            hl = data.get("highlights")
            hl = (
                [str(h).strip() for h in hl if isinstance(h, str) and str(h).strip()]
                if isinstance(hl, list)
                else []
            )
            kt = str(data.get("key_takeaway", "")).strip()
            if paras:
                return {"paragraphs": paras, "key_takeaway": kt, "highlights": hl}
    except Exception:
        pass
    return {"paragraphs": [], "key_takeaway": "", "highlights": []}


# ── Charts — all driven by real analysis output ───────────────────────────────
def _build_charts(brands, analysis, sentiment, claims=None) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    ev_by_field: Dict[str, List[str]] = {}
    for c in claims or []:
        ev_by_field.setdefault(c.get("field", ""), []).extend(c.get("evidence_ids", []))

    def eids(*fields: str) -> List[str]:
        out: List[str] = []
        for f in fields:
            out.extend(ev_by_field.get(f, []))
        seen = set()
        return [x for x in out if not (x in seen or seen.add(x))][:6]

    comp = analysis.get("comparison") or {}
    dims = comp.get("dimensions") or []
    scores = [
        s
        for s in (comp.get("scores") or [])
        if isinstance(s.get("values"), list) and len(s["values"]) == len(dims) and dims
    ]
    if dims and scores:
        title = "Capability comparison"
        specs.append(
            {
                "chart_id": _sid("ch"), "type": "radar", "title": title,
                "option": C.feature_radar(
                    title, dims,
                    [{"name": s["brand"], "values": s["values"]} for s in scores[:4]],
                ),
                "evidence_ids": eids("feature_tree", "overview"),
            }
        )

    pricing = [p for p in (analysis.get("pricing") or []) if p.get("entry_price") is not None]
    if pricing:
        title = "Entry-tier pricing"
        specs.append(
            {
                "chart_id": _sid("ch"), "type": "bar", "title": title,
                "option": C.pricing_bar(
                    title, [p["brand"] for p in pricing],
                    [float(p["entry_price"]) for p in pricing],
                ),
                "evidence_ids": eids("pricing_model"),
            }
        )

    share = [
        s for s in (analysis.get("market_share") or [])
        if isinstance(s.get("value"), (int, float))
    ]
    if share:
        title = "Estimated market share (analyst inference)"
        specs.append(
            {
                "chart_id": _sid("ch"), "type": "donut", "title": title,
                "option": C.market_donut(
                    title, [{"name": s["name"], "value": s["value"]} for s in share]
                ),
                "evidence_ids": eids("overview"),
            }
        )

    ff = analysis.get("five_forces") or {}
    if any(
        isinstance(ff.get(k), (int, float))
        for k in ("rivalry", "new_entrants", "substitutes", "buyer_power", "supplier_power")
    ):
        title = "Porter's five forces"
        specs.append(
            {
                "chart_id": _sid("ch"), "type": "five_forces", "title": title,
                "option": C.five_forces_radar(title, ff),
                "evidence_ids": eids("overview"),
            }
        )

    tr = analysis.get("trends") or {}
    tx = tr.get("x") if isinstance(tr.get("x"), list) else []
    tseries = [
        s for s in (tr.get("series") or [])
        if isinstance(s.get("values"), list) and len(s["values"]) == len(tx) and tx
    ]
    if tx and tseries:
        unit = tr.get("unit", "")
        title = f"Trajectory ({unit})" if unit else "Trajectory"
        specs.append(
            {
                "chart_id": _sid("ch"), "type": "trend", "title": title,
                "option": C.trend_line(
                    title, tx,
                    [{"name": s["name"], "values": s["values"]} for s in tseries[:5]],
                    y_name=unit,
                ),
                "evidence_ids": eids("trend", "overview"),
            }
        )

    if sentiment.get("sample_size"):
        title = "Overall sentiment"
        specs.append(
            {
                "chart_id": _sid("ch"), "type": "sentiment_donut", "title": title,
                "option": C.sentiment_donut(title, sentiment["overall_count"]),
                "evidence_ids": [],
            }
        )
        if sentiment.get("by_platform"):
            title = "Volume by platform"
            specs.append(
                {
                    "chart_id": _sid("ch"), "type": "platform_bar", "title": title,
                    "option": C.platform_bar(title, sentiment["by_platform"]),
                    "evidence_ids": [],
                }
            )
    return specs


# ── Exportable data grids for data-dense sections ─────────────────────────────
def _build_data_grid(
    section_id: str, analysis: Dict[str, Any], evidences: List[Evidence]
) -> Optional[Dict[str, Any]]:
    ev_by_id = {e.evidence_id: e for e in evidences}

    def _src(eids):
        for eid in eids or []:
            e = ev_by_id.get(eid)
            if e:
                return domain_of(e.source_url), e.source_url, eid
        return "", "", ""

    columns = ["Item", "Value", "Metric", "Source", "Source URL"]
    rows: List[Dict[str, Any]] = []
    structured = analysis.get("structured") or {}

    if section_id == "pricing":
        for pm in structured.get("pricing_model", []):
            brand = pm.get("brand", "")
            for t in pm.get("tiers", []):
                src, url, eid = _src(t.get("evidence_ids"))
                price = t.get("price")
                currency = pm.get("currency", "USD")
                symbol = "$" if currency == "USD" else f"{currency} "
                rows.append(
                    {
                        "name": f"{brand} · {t.get('name','')}",
                        "value": (
                            f"{symbol}{price}/{t.get('period','month')}"
                            if price is not None
                            else "Not published"
                        ),
                        "metric": "Pricing tier",
                        "source": src, "source_url": url, "evidence_id": eid,
                    }
                )
    elif section_id == "feature":
        comp = analysis.get("comparison") or {}
        dims = comp.get("dimensions") or []
        for s in comp.get("scores") or []:
            vals = s.get("values") or []
            for i, dim in enumerate(dims):
                if i < len(vals):
                    rows.append(
                        {
                            "name": f"{s.get('brand','')} · {dim}",
                            "value": vals[i],
                            "metric": "Capability score (0-100)",
                            "source": "Analyst assessment",
                            "source_url": "", "evidence_id": "",
                        }
                    )
    elif section_id == "overview":
        for sh in analysis.get("market_share") or []:
            rows.append(
                {
                    "name": f"{sh.get('name','')} market share",
                    "value": f"{sh.get('value','')}%",
                    "metric": "Estimated share",
                    "source": "Analyst inference",
                    "source_url": "", "evidence_id": "",
                }
            )
    elif section_id == "trend":
        tr = analysis.get("trends") or {}
        tx = tr.get("x") or []
        for s in tr.get("series") or []:
            vals = s.get("values") or []
            for i, x in enumerate(tx):
                if i < len(vals):
                    rows.append(
                        {
                            "name": f"{s.get('name','')} · {x}",
                            "value": vals[i],
                            "metric": tr.get("unit", "Trend value"),
                            "source": "Analyst inference",
                            "source_url": "", "evidence_id": "",
                        }
                    )

    if len(rows) < 2:
        return None
    return {"columns": columns, "rows": rows}


def _cover_image(brands: List[str], report_id: str) -> str:
    """A self-contained SVG cover, derived from the report itself.

    Kept as an inline data URI so a report never depends on an external image
    host staying up — and so an offline deployment still renders.
    """
    palette = [
        ("#7C9885", "#5E7A66"), ("#8FA8C0", "#5E7A9B"), ("#C2B59B", "#9B8C6E"),
        ("#CE9A92", "#A8746C"), ("#A8C0A8", "#7C9885"),
    ]
    start, end = palette[sum(ord(c) for c in report_id) % len(palette)]
    label = " · ".join(brands[:3])[:48]
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 675'>"
        f"<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
        f"<stop offset='0' stop-color='{start}'/><stop offset='1' stop-color='{end}'/>"
        "</linearGradient></defs>"
        "<rect width='1200' height='675' fill='url(#g)'/>"
        "<circle cx='980' cy='140' r='220' fill='#ffffff' opacity='0.07'/>"
        "<circle cx='220' cy='560' r='170' fill='#ffffff' opacity='0.05'/>"
        "<text x='72' y='352' font-family='Georgia,serif' font-size='58' "
        f"fill='#ffffff' opacity='0.96'>{_xml_escape(label)}</text>"
        "<text x='74' y='404' font-family='Inter,sans-serif' font-size='23' "
        "fill='#ffffff' opacity='0.72' letter-spacing='3'>COMPETITIVE INTELLIGENCE</text>"
        "</svg>"
    )
    return "data:image/svg+xml;utf8," + quote(svg)


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&apos;")
    )


# ── Report assembly ───────────────────────────────────────────────────────────
def _assemble_report(
    query, brands, focus, dispatch, claims, evidences, images, sentiment, charts,
    sections_text, collect_notes, analysis, metrics, quality_before, quality_after,
    trace_spans, mode, section_ids, sentiment_text=None,
) -> Dict[str, Any]:
    rid = _sid("r")
    members = [m["id"] for m in dispatch["members"]]
    title = f"{', '.join(brands)}: Competitive Landscape Analysis"
    indep_domains = len({domain_of(e.source_url) for e in evidences if e.source_url})
    subtitle = (
        f"{len(evidences)} sources · {indep_domains} independent domains · "
        f"{len(members)} analysts · {MODE_CONFIG.get(mode,{}).get('label','Deep')} mode"
    )

    def claims_for(*fields: str):
        fs = set(fields)
        return [c for c in claims if c["field"] in fs]

    chart_by_type = {c["type"]: c for c in charts}
    title_map = dict(SECTION_PLAN)

    sec_meta = {
        "summary": (("overview",), ()),
        "overview": (("overview",), ("five_forces", "donut")),
        "feature": (("feature_tree",), ("radar",)),
        "pricing": (("pricing_model",), ("bar",)),
        "persona": (("user_persona",), ()),
        "trend": (("trend",), ("trend",)),
        "swot": (("swot",), ()),
        "moat": (("overview", "feature_tree", "swot"), ()),
        "inflection": (("trend", "overview"), ()),
        "contrarian": (("overview", "swot", "trend"), ()),
        "conclusion": (("conclusion",), ()),
        "risk": ((), ()),
        "persp_pm": (("feature_tree", "overview"), ()),
        "persp_ops": (("overview", "trend"), ()),
        "persp_sales": (("feature_tree", "pricing_model"), ()),
        "persp_user": (("user_persona", "feature_tree"), ()),
        "persp_investor": (("overview", "trend", "swot"), ()),
    }
    data_grid_sections = {"pricing", "feature", "overview", "trend"}

    def _section(sid: str):
        fields, chart_types = sec_meta.get(sid, ((), ()))
        st = sections_text.get(sid, {}) if isinstance(sections_text, dict) else {}
        if not isinstance(st, dict):
            st = {
                "paragraphs": st if isinstance(st, list) else [str(st)],
                "key_takeaway": "", "highlights": [],
            }
        sec_claims = claims_for(*fields)
        sec_charts = [chart_by_type[t] for t in chart_types if t in chart_by_type]
        src: List[str] = []
        for c in sec_claims:
            src.extend(c.get("evidence_ids", []))
        for ch in sec_charts:
            src.extend(ch.get("evidence_ids", []))
        seen = set()
        src = [x for x in src if not (x in seen or seen.add(x))]
        sec = {
            "id": sid, "title": title_map.get(sid, sid), "level": 1,
            "key_takeaway": st.get("key_takeaway", ""),
            "highlights": st.get("highlights", []),
            "paragraphs": st.get("paragraphs", []),
            "claims": sec_claims,
            "charts": sec_charts,
            "source_evidence_ids": src,
            "structured": None,
            "data_grid": None,
        }
        structured = analysis.get("structured") or {}
        if sid == "feature" and structured.get("feature_tree"):
            sec["structured"] = {"type": "feature_tree", "data": structured["feature_tree"]}
        elif sid == "pricing" and structured.get("pricing_model"):
            sec["structured"] = {"type": "pricing_model", "data": structured["pricing_model"]}
        elif sid == "persona" and structured.get("user_persona"):
            sec["structured"] = {"type": "user_persona", "data": structured["user_persona"]}
        if sid in data_grid_sections:
            sec["data_grid"] = _build_data_grid(sid, analysis, evidences)
        return sec

    sections = [_section(sid) for sid in section_ids if sid != "sentiment"]

    sent_charts = [
        c
        for c in (chart_by_type.get("sentiment_donut"), chart_by_type.get("platform_bar"))
        if c
    ]
    st = sentiment_text or {}
    has_sample = bool(sentiment.get("sample_size"))
    sent_paras = [p for p in st.get("paragraphs", []) if str(p).strip()]
    if not sent_paras:
        if has_sample:
            sent_paras = [
                f"Sentiment analysis across {sentiment.get('sample_size', 0)} real "
                "comments, each linked to its source so any quote can be checked. "
                "The breakdown by platform, the opinion split and representative "
                "verbatims follow."
            ]
        else:
            sent_paras = [
                "No linked user comments could be retrieved for this research, so "
                "no quantitative sentiment conclusion is offered. Stating a number "
                "here without the underlying comments would violate the "
                "no-claim-without-evidence rule."
            ]
    sent_takeaway = st.get("key_takeaway") or (
        (
            f"Across {sentiment.get('sample_size', 0)} real comments: "
            f"{sentiment.get('overall', {}).get('pos', 0)}% positive, "
            f"{sentiment.get('overall', {}).get('neu', 0)}% neutral, "
            f"{sentiment.get('overall', {}).get('neg', 0)}% negative."
        )
        if has_sample
        else ""
    )
    sentiment_sec = {
        "id": "sentiment", "title": "User Sentiment and Opinion Camps", "level": 1,
        "key_takeaway": sent_takeaway,
        "highlights": [h for h in st.get("highlights", []) if str(h).strip()],
        "paragraphs": sent_paras,
        "claims": [], "charts": sent_charts, "source_evidence_ids": [],
        "structured": None, "data_grid": None,
    }
    insert_at = len(sections)
    for i, s in enumerate(sections):
        if s["id"] in ("conclusion", "risk"):
            insert_at = i
            break
    sections.insert(insert_at, sentiment_sec)

    if collect_notes:
        sections.append(
            {
                "id": "trace_note", "title": "Appendix: Collection Notes", "level": 1,
                "key_takeaway": "", "highlights": [], "paragraphs": collect_notes,
                "claims": [], "charts": [], "source_evidence_ids": [],
                "structured": None, "data_grid": None,
            }
        )

    toc = [{"id": s["id"], "title": s["title"], "level": 1} for s in sections]
    glossary = [
        {
            "term": "Cross-validation",
            "definition": "A conclusion supported by two or more independent domains, "
                          "which is the only path to high confidence.",
            "source": "Vantage iron rules",
        },
        {
            "term": "No claim without evidence",
            "definition": "Every factual conclusion carries evidence ids, or it is "
                          "marked unverified rather than asserted.",
            "source": "Vantage iron rules",
        },
        {
            "term": "Opinion camps",
            "definition": "Real user comments clustered by stance, with normalized "
                          "shares and representative quotes.",
            "source": "Sentiment pipeline",
        },
        {
            "term": "SCP framework",
            "definition": "Structure-Conduct-Performance, the industrial-organization "
                          "model linking market structure to firm behavior and results.",
            "source": "Bain / Scherer",
        },
        {
            "term": "Porter's five forces",
            "definition": "Competitive pressure assessed across rivalry, new entrants, "
                          "substitutes, buyer power and supplier power.",
            "source": "Michael Porter",
        },
    ]

    evidence_dicts = []
    for e in evidences:
        d = e.to_dict()
        d["domain"] = domain_of(e.source_url)
        evidence_dicts.append(d)

    figures = _curate_figures(images, limit=12)
    if figures:
        toc.append({"id": "figures", "title": "Collected Imagery", "level": 1})

    # Trimmed trace for the report payload — full prompts stay in the DB.
    trace_lite = [
        {
            "span_id": s["span_id"], "seq": s["seq"], "agent_id": s["agent_id"],
            "stage": s["stage"], "purpose": s["purpose"], "model": s["model"],
            "prompt": s["prompt"][:300], "response": s["response"][:300],
            "prompt_tokens": s["prompt_tokens"],
            "completion_tokens": s["completion_tokens"],
            "total_tokens": s["total_tokens"], "latency_ms": s["latency_ms"],
            "decision": s["decision"], "evidence_ids": s["evidence_ids"], "ts": s["ts"],
        }
        for s in trace_spans
    ]

    return {
        "id": rid,
        "title": title,
        "subtitle": subtitle,
        "query": query,
        "brands": brands,
        "mode": mode,
        "created_at": _now(),
        "experts": members,
        "dispatch": dispatch["members"],
        "cover_image": _cover_image(brands, rid),
        "toc": toc,
        "sections": sections,
        "charts": charts,
        "evidence": evidence_dicts,
        "claims": claims,
        "sentiment": sentiment,
        "glossary": glossary,
        "figures": figures,
        "structured": analysis.get("structured") or {},
        "metrics": metrics,
        "quality_before": quality_before,
        "quality_after": quality_after,
        "trace": trace_lite,
    }


def _curate_figures(
    images: List[Dict[str, Any]], limit: int = 12
) -> List[Dict[str, Any]]:
    """De-duplicate by URL and round-robin across brands so no one dominates."""
    seen: set = set()
    by_brand: Dict[str, List[Dict[str, Any]]] = {}
    for im in images:
        src = (im.get("src") or "").strip()
        if not src or src in seen:
            continue
        seen.add(src)
        by_brand.setdefault(im.get("brand", ""), []).append(im)
    out: List[Dict[str, Any]] = []
    idx = 0
    while len(out) < limit:
        added = False
        for brand in list(by_brand.keys()):
            lst = by_brand[brand]
            if idx < len(lst):
                out.append(lst[idx])
                added = True
                if len(out) >= limit:
                    break
        if not added:
            break
        idx += 1
    return out
