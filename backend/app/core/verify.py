"""Post-write verification of the written report.

`check_sections` runs deterministic checks over the finished prose and repairs
what can be repaired mechanically. `llm_report_review` adds an editor's read for
the failures rules cannot see — an assertion with nothing behind it, two
sections reaching opposite verdicts. `sections_to_rewrite` turns whatever is
left into a rewrite list.

This is the artifact-side counterpart to `audit.py`. Audit gates the *analysis*
before it is written up; verify gates the *document* that came out. Nothing here
routes work back to collection or analysis: a section that fails is rewritten
against the same evidence, and anything still failing after the rewrite budget
is reported rather than quietly shipped.

The citation checker is the reason this module exists. The writer is told to
mark supporting evidence inline as `[e_xxxx]`, and it does — but nothing
downstream ever validated those ids, so a fabricated one read exactly like a
real one. Here real ids are normalized and collected per section (the report
links them), and ids that match no evidence are removed.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

# Severity ladder. `cosmetic` is repaired in place and never triggers a rewrite;
# `minor` needs two in one section to be worth a model call; `major` always is.
SEV_COSMETIC = "cosmetic"
SEV_MINOR = "minor"
SEV_MAJOR = "major"

_SEVERITY_WEIGHT = {SEV_MAJOR: 4, SEV_MINOR: 1, SEV_COSMETIC: 0}

# Score dimension keys. The frontend's verify panel renders these directly, so
# they are part of the API contract — changing one is a cross-stack change.
DIM_CITATION = "Citation integrity"
DIM_CONSISTENCY = "Internal consistency"
DIM_SUPPORT = "Evidence support"
DIM_EDITORIAL = "Editorial quality"

# Findings the model is allowed to raise. Anything else is normalized to `other`
# so the frontend never has to render an unbounded vocabulary.
LLM_KINDS = ("unsupported", "contradiction", "overstated", "vague", "repetition", "other")


@dataclass
class Finding:
    """One defect in the written report, tied to the section it lives in."""

    section_id: str
    severity: str  # cosmetic | minor | major
    kind: str
    detail: str
    fix: str = ""
    auto_fixed: bool = False
    raised_by: str = "L3-003"
    finding_id: str = field(default_factory=lambda: "vf_" + uuid.uuid4().hex[:8])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "section_id": self.section_id,
            "severity": self.severity,
            "kind": self.kind,
            "detail": self.detail,
            "fix": self.fix,
            "auto_fixed": self.auto_fixed,
            "raised_by": self.raised_by,
        }


@dataclass
class VerifyReport:
    findings: List[Finding] = field(default_factory=list)
    #: section id -> the valid evidence ids cited in its prose, in first-use order.
    citations: Dict[str, List[str]] = field(default_factory=dict)
    paragraph_counts: Dict[str, int] = field(default_factory=dict)
    counters: Dict[str, int] = field(default_factory=dict)

    def add(self, f: Finding) -> None:
        self.findings.append(f)

    def bump(self, key: str, by: int = 1) -> None:
        self.counters[key] = self.counters.get(key, 0) + by

    def replace_section(self, sid: str, other: "VerifyReport") -> None:
        """Swap in the check results for a section that was rewritten.

        Findings, citations and totals for `sid` all move to the accepted draft,
        so what the report shows describes the document that ships rather than
        the drafts discarded along the way. Dropped citations are the exception
        and stay cumulative: every dead marker removed is a real repair.
        """
        self.findings = [f for f in self.findings if f.section_id != sid]
        self.findings.extend(other.findings)
        self.bump("citations_kept", len(other.citations.get(sid, [])) - len(self.citations.get(sid, [])))
        self.bump("citations_dropped", other.counters.get("citations_dropped", 0))
        self.bump(
            "paragraphs_checked",
            other.paragraph_counts.get(sid, 0) - self.paragraph_counts.get(sid, 0),
        )
        self.citations[sid] = other.citations.get(sid, [])
        self.paragraph_counts[sid] = other.paragraph_counts.get(sid, 0)

    @property
    def fixed(self) -> List[Finding]:
        return [f for f in self.findings if f.auto_fixed]

    @property
    def open(self) -> List[Finding]:
        return [f for f in self.findings if not f.auto_fixed]

    @property
    def majors(self) -> List[Finding]:
        return [f for f in self.open if f.severity == SEV_MAJOR]

    def for_section(self, sid: str) -> List[Finding]:
        return [f for f in self.findings if f.section_id == sid]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "citations": self.citations,
            "counters": dict(self.counters),
        }

    def summary(self) -> Dict[str, int]:
        """Condensed counts for the report's verification card."""
        return {
            "sections_checked": self.counters.get("sections_checked", 0),
            "paragraphs_checked": self.counters.get("paragraphs_checked", 0),
            "citations_resolved": self.counters.get("citations_kept", 0),
            "citations_dropped": self.counters.get("citations_dropped", 0),
            "auto_fixed": len(self.fixed),
            "open_findings": len(self.open),
        }


def score_findings(findings: Sequence[Finding]) -> int:
    """Weighted defect load. Used to decide whether a rewrite actually helped."""
    return sum(_SEVERITY_WEIGHT.get(f.severity, 0) for f in findings if not f.auto_fixed)


# ── Deterministic checks ──────────────────────────────────────────────────────
# An evidence id as the writer emits it: `e_` plus the hex tail of a uuid4.
_CITE_TOKEN = re.compile(r"^e_[0-9a-z]{4,20}$", re.I)
_BRACKET = re.compile(r"\[([^\[\]\n]{1,240})\]")
_BARE_ID = re.compile(r"(?<![\w\[])e_[0-9a-f]{4,20}\b", re.I)
_SLOT = "\x00{}\x00"

_TERMINAL = ('.', '!', '?', '"', "'", '”', '’', ')', ']', '…', '。', '！', '？', '」', '』')
_PLACEHOLDER_RE = re.compile(
    r"(\bTODO\b|\bFIXME\b|lorem ipsum|\[insert|placeholder text|"
    r"as an AI|as a language model|I'm sorry, |I cannot provide)",
    re.I,
)
_GENERATION_FAILED = re.compile(r"could not be generated", re.I)
_PERCENT_RE = re.compile(r"(\d{1,6}(?:\.\d+)?)\s*%")
# A percentage over 100 is only wrong when it is a share of something. Growth,
# increases and multiples legitimately exceed 100%, so the check reads the words
# around the number instead of the number alone.
_SHARE_CONTEXT = re.compile(
    r"(share|penetration|of (the )?(market|users|respondents|customers|revenue|"
    r"traffic|downloads|installs)|of all\b)",
    re.I,
)


def _fix_citations(text: str, valid_ids: Set[str]) -> Tuple[str, List[str], int]:
    """Normalize `[e_xxxx]` markers; drop ids that match no collected evidence.

    Returns the cleaned text, the ids kept in first-use order, and how many were
    dropped. Brackets whose contents are not all id-shaped are left untouched —
    `[1]` or `[see below]` are the writer's prose, not a citation.
    """
    kept: List[str] = []
    dropped = 0
    slots: List[str] = []

    def _slot(ids: List[str]) -> str:
        slots.append(", ".join(ids))
        return _SLOT.format(len(slots) - 1)

    def _bracket_repl(m: "re.Match[str]") -> str:
        nonlocal dropped
        tokens = [t.strip() for t in re.split(r"[,;/|]+", m.group(1)) if t.strip()]
        if not tokens or not all(_CITE_TOKEN.match(t) for t in tokens):
            return m.group(0)
        good: List[str] = []
        for t in tokens:
            tl = t.lower()
            if tl in valid_ids:
                if tl not in good:
                    good.append(tl)
            else:
                dropped += 1
        if not good:
            return ""
        kept.extend(good)
        return _slot(good)

    out = _BRACKET.sub(_bracket_repl, text)

    # A bare `e_xxxx` outside brackets is the same citation with lost syntax:
    # give it brackets if it is real, remove it if it is not.
    def _bare_repl(m: "re.Match[str]") -> str:
        nonlocal dropped
        tid = m.group(0).lower()
        if tid in valid_ids:
            kept.append(tid)
            return _slot([tid])
        dropped += 1
        return ""

    out = _BARE_ID.sub(_bare_repl, out)
    for i, ids in enumerate(slots):
        out = out.replace(_SLOT.format(i), f"[{ids}]")
    return out, kept, dropped


def _strip_markdown(text: str) -> str:
    """Remove markup the report renders as literal text — it is plain prose."""
    t = re.sub(r"^\s{0,3}#{1,6}\s+", "", text)
    t = re.sub(r"^\s{0,3}[-*•]\s+", "", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"(?<!\w)__(.+?)__(?!\w)", r"\1", t)
    t = re.sub(r"(?<!\*)\*(\S(?:.*?\S)?)\*(?!\*)", r"\1", t)
    return t.replace("`", "")


def _tidy(text: str) -> str:
    t = text.replace("\\n", " ").replace(" ", " ")
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r" {2,}", " ", t)
    return t.strip()


def _clean_block(
    text: str, valid_ids: Set[str]
) -> Tuple[str, List[str], int, bool]:
    """-> (clean text, cited ids, dropped ids, formatting was changed)."""
    md = _strip_markdown(text)
    cited_text, kept, dropped = _fix_citations(md, valid_ids)
    final = _tidy(cited_text)
    fmt_changed = md != text or _tidy(md) != md.strip()
    return final, kept, dropped, fmt_changed


def _looks_truncated(text: str) -> bool:
    """A paragraph that stops mid-sentence — usually a token-limit cutoff."""
    t = re.sub(r"\[[^\]]*\]\s*$", "", text).strip()
    return bool(t) and not t.endswith(_TERMINAL)


def _fingerprint(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())[:140]


def check_sections(
    sections: Dict[str, Dict[str, Any]],
    titles: Dict[str, str],
    valid_ids: Set[str],
    *,
    min_paragraphs: int = 3,
    check_duplicates: bool = True,
    inline_citation_exempt: Optional[Set[str]] = None,
) -> Tuple[Dict[str, Dict[str, Any]], VerifyReport]:
    """Check and repair the written sections. Returns cleaned copies plus findings.

    Mechanical defects — dead citations, leftover markdown, doubled spacing — are
    fixed here and recorded as `auto_fixed`. Everything else is left for the
    rewrite pass, because repairing an unsupported sentence in code would mean
    guessing what the analyst meant.

    `inline_citation_exempt` names sections whose sources hang off the section
    itself rather than off sentences in it — the sentiment narrative interprets a
    computed table where every quote already carries its link — so "cites
    nothing" is not a defect there.
    """
    exempt = inline_citation_exempt or set()
    vr = VerifyReport()
    cleaned: Dict[str, Dict[str, Any]] = {}
    fingerprints: Dict[str, str] = {}

    for sid, st in sections.items():
        title = titles.get(sid, sid)
        st = st if isinstance(st, dict) else {}
        cited: List[str] = []
        fmt_hits = 0
        dropped_here = 0
        vr.bump("sections_checked")

        def _pass(raw: Any) -> str:
            nonlocal fmt_hits, dropped_here
            text, ids, dropped, changed = _clean_block(str(raw), valid_ids)
            for i in ids:
                if i not in cited:
                    cited.append(i)
            dropped_here += dropped
            if changed:
                fmt_hits += 1
            return text

        paragraphs = [p for p in (_pass(x) for x in (st.get("paragraphs") or [])) if p]
        key_takeaway = _pass(st.get("key_takeaway") or "")
        highlights = [h for h in (_pass(x) for x in (st.get("highlights") or [])) if h]

        cleaned[sid] = {
            "paragraphs": paragraphs,
            "key_takeaway": key_takeaway,
            "highlights": highlights,
        }
        vr.citations[sid] = cited
        vr.paragraph_counts[sid] = len(paragraphs)
        vr.bump("citations_kept", len(cited))
        vr.bump("paragraphs_checked", len(paragraphs))

        if dropped_here:
            vr.bump("citations_dropped", dropped_here)
            vr.add(
                Finding(
                    sid, SEV_MINOR, "citation",
                    f"\"{title}\" cited {dropped_here} evidence id(s) that match no "
                    "collected source. The markers were removed so the report "
                    "does not point at evidence that does not exist.",
                    auto_fixed=True,
                )
            )
        if fmt_hits:
            vr.add(
                Finding(
                    sid, SEV_COSMETIC, "formatting",
                    f"\"{title}\" carried markup or spacing artifacts in "
                    f"{fmt_hits} block(s); normalized to plain prose.",
                    auto_fixed=True,
                )
            )

        # ---- structural and content checks (not auto-fixable) ----
        if not paragraphs:
            vr.add(
                Finding(
                    sid, SEV_MAJOR, "empty",
                    f"\"{title}\" has no body text at all.",
                    fix="Write the section from the evidence.",
                )
            )
            continue

        body = " ".join(paragraphs)
        if _GENERATION_FAILED.search(body):
            vr.add(
                Finding(
                    sid, SEV_MAJOR, "generation_failed",
                    f"\"{title}\" contains the writer's failure placeholder instead "
                    "of analysis.",
                    fix="Write the section from scratch.",
                )
            )
        for p in paragraphs:
            if _looks_truncated(p):
                vr.add(
                    Finding(
                        sid, SEV_MAJOR, "truncated",
                        f"\"{title}\" has a paragraph that stops mid-sentence: "
                        f"\"...{p[-70:]}\"",
                        fix="Finish the argument; keep every paragraph a complete thought.",
                    )
                )
                break
        if _PLACEHOLDER_RE.search(body) or _PLACEHOLDER_RE.search(key_takeaway):
            vr.add(
                Finding(
                    sid, SEV_MINOR, "placeholder",
                    f"\"{title}\" contains placeholder or assistant-voice text.",
                    fix="Replace it with the actual finding, or say the data is missing.",
                )
            )
        if len(paragraphs) < min_paragraphs:
            vr.add(
                Finding(
                    sid, SEV_MINOR, "thin",
                    f"\"{title}\" runs {len(paragraphs)} paragraph(s) against a "
                    f"{min_paragraphs}-paragraph floor for this research mode.",
                    fix=f"Develop the argument to at least {min_paragraphs} paragraphs.",
                )
            )
        if not key_takeaway:
            vr.add(
                Finding(
                    sid, SEV_MINOR, "no_takeaway",
                    f"\"{title}\" opens without a key takeaway, so the section "
                    "does not answer first.",
                    fix="Lead with the single sharpest judgement.",
                )
            )
        if not cited and sid not in exempt:
            vr.add(
                Finding(
                    sid, SEV_MINOR, "uncited",
                    f"\"{title}\" cites no evidence anywhere in its prose.",
                    fix="Mark the supporting evidence id after each key conclusion.",
                )
            )
        for m in _PERCENT_RE.finditer(body):
            value = float(m.group(1))
            if value <= 100:
                continue
            window = body[max(0, m.start() - 60) : m.end() + 40]
            if value > 1000 or _SHARE_CONTEXT.search(window):
                vr.add(
                    Finding(
                        sid, SEV_MAJOR, "numeric",
                        f"\"{title}\" states an impossible share of {m.group(1)}%: "
                        f"\"...{window.strip()}...\"",
                        fix="Correct the figure against the evidence, or drop it.",
                    )
                )
                break

        if check_duplicates:
            for p in paragraphs:
                fp = _fingerprint(p)
                if len(fp) < 60:
                    continue
                prior = fingerprints.get(fp)
                if prior and prior != sid:
                    vr.add(
                        Finding(
                            sid, SEV_MINOR, "duplicate",
                            f"\"{title}\" repeats a paragraph already used in "
                            f"\"{titles.get(prior, prior)}\".",
                            fix="Say something new here, or cross-reference instead of repeating.",
                        )
                    )
                    break
                fingerprints.setdefault(fp, sid)

    return cleaned, vr


# ── Editorial review ──────────────────────────────────────────────────────────
def _report_digest(
    sections: Dict[str, Dict[str, Any]],
    titles: Dict[str, str],
    order: Sequence[str],
    notes: Optional[Dict[str, str]] = None,
    body_chars: int = 700,
) -> str:
    out = []
    for sid in order:
        st = sections.get(sid)
        if not st:
            continue
        body = " ".join(st.get("paragraphs") or [])
        note = (notes or {}).get(sid)
        out.append(
            f"[{sid}] {titles.get(sid, sid)}\n"
            + (f"  note: {note}\n" if note else "")
            + f"  takeaway: {st.get('key_takeaway') or '(none)'}\n"
            f"  body: {body[:body_chars]}"
        )
    return "\n\n".join(out) or "(no sections)"


def llm_report_review(
    query: str,
    brands: List[str],
    sections: Dict[str, Dict[str, Any]],
    titles: Dict[str, str],
    order: Sequence[str],
    claims: List[Dict[str, Any]],
    vr: VerifyReport,
    model: Optional[str] = None,
    section_notes: Optional[Dict[str, str]] = None,
    persona: str = "",
) -> Dict[str, Any]:
    """A copy editor's read of the finished document.

    Rules catch dead citations and broken structure. They cannot tell whether the
    conclusion in section 7 contradicts the one in section 1, or whether a
    confident number is actually backed by anything, so this asks a model to read
    the whole report at once — the only stage that ever sees it whole. Falls back
    to a rules-only verdict when the call fails.

    `persona` is the quality officer's preamble, built by the caller so this
    module stays independent of the roster.
    """
    from app.core.llm import chat_json

    claim_lines = (
        "\n".join(
            f"- [{c.get('confidence','?')}] {c.get('text','')} "
            f"(sources: {', '.join(c.get('evidence_ids') or []) or 'none'})"
            for c in claims[:16]
        )
        or "(no claims)"
    )
    open_rule_findings = [f for f in vr.open][:6]
    rule_lines = (
        "\n".join(f"- [{f.severity}] {f.detail}" for f in open_rule_findings)
        or "(rules found nothing outstanding)"
    )
    # Deliberately free of counts: this text is shown next to the final tallies,
    # which keep moving as sections are rewritten after the review runs.
    fallback = {
        "verdict": "revise" if vr.majors else "pass",
        "scores": _rule_scores(vr),
        "review": (
            "The editorial read could not run — the model was unavailable or out "
            "of quota — so this verdict rests on the automated checks alone. "
            "Citation validity, formatting and structure were still verified; "
            "cross-section consistency was not."
        ),
        "findings": [],
    }

    try:
        data = chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        (
                            persona
                            or "You are the quality officer on a competitive-"
                            "intelligence team.\n\n"
                        )
                        + "You are reading the finished report before it ships. "
                        "You are the only reviewer who sees every section at "
                        "once, so cross-section problems are yours to catch.\n\n"
                        "Look for, in priority order:\n"
                        "1. CONTRADICTION — two sections reaching opposite verdicts "
                        "on the same question (who leads, who is cheaper, where the "
                        "market is going), or a conclusion that contradicts the "
                        "claim list.\n"
                        "2. UNSUPPORTED — a specific figure, share, growth rate or "
                        "confident verdict with no cited evidence id nearby and no "
                        "matching claim.\n"
                        "3. OVERSTATED — a hedged or low-confidence claim restated "
                        "as settled fact.\n"
                        "4. VAGUE — a sentence that would be true of any company in "
                        "any market.\n"
                        "5. REPETITION — the same point made twice across sections.\n\n"
                        "Judge only what is in front of you. Do not invent problems "
                        "to look thorough: a clean report should come back with an "
                        "empty findings list and a 'pass' verdict. Reference each "
                        "finding by the bracketed section id. Where a section "
                        "carries a `note`, it explains where that section's numbers "
                        "come from — respect it and do not report those figures as "
                        "unsupported.\n\n"
                        "Severity: 'major' for contradictions and unsupported "
                        "quantitative or verdict-level assertions; 'minor' for "
                        "everything else.\n\n"
                        "Score each dimension 0-100 as an integer, using the full "
                        "range rather than round multiples of ten.\n\n"
                        'Return JSON only: {"verdict":"pass|revise","scores":'
                        f'{{"{DIM_CITATION}":int,"{DIM_CONSISTENCY}":int,'
                        f'"{DIM_SUPPORT}":int,"{DIM_EDITORIAL}":int}},'
                        '"review":"one paragraph on what holds up and what does not",'
                        '"findings":[{"section_id":"the id in brackets",'
                        '"severity":"major|minor",'
                        '"kind":"unsupported|contradiction|overstated|vague|repetition",'
                        '"detail":"the specific problem, quoting the text",'
                        '"fix":"what the rewrite should do"}]}'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Research topic: {query}\n"
                        f"Competitors: {', '.join(brands)}\n\n"
                        f"Claims the analysis established:\n{claim_lines}\n\n"
                        f"Defects the automated checks already found:\n{rule_lines}\n\n"
                        f"The report as written:\n\n"
                        f"{_report_digest(sections, titles, order, section_notes)}"
                    ),
                },
            ],
            max_tokens=3000,
            temperature=0.2,
            model=model,
            purpose="Verify the written report: citations, consistency, support",
        )
        if isinstance(data, dict) and (data.get("scores") or data.get("findings")):
            scores = {str(k): _clamp(v) for k, v in (data.get("scores") or {}).items()}
            return {
                "verdict": "revise" if str(data.get("verdict")) == "revise" else "pass",
                "scores": scores or fallback["scores"],
                "review": str(data.get("review") or fallback["review"]),
                "findings": _coerce_findings(data.get("findings"), sections),
            }
    except Exception:
        pass
    return fallback


def _rule_scores(vr: VerifyReport) -> Dict[str, int]:
    """Scores derived from the rule checks alone, for when the model call fails."""
    kept = vr.counters.get("citations_kept", 0)
    dropped = vr.counters.get("citations_dropped", 0)
    citation = round(100 * kept / (kept + dropped)) if (kept + dropped) else 60
    open_load = score_findings(vr.open)
    editorial = max(0, 100 - 8 * open_load)
    return {
        DIM_CITATION: citation,
        DIM_CONSISTENCY: 70,
        DIM_SUPPORT: max(0, 100 - 10 * len(vr.majors)),
        DIM_EDITORIAL: editorial,
    }


def _clamp(v: Any) -> int:
    try:
        return max(0, min(100, int(round(float(v)))))
    except (TypeError, ValueError):
        return 0


def _coerce_findings(
    raw: Any, sections: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Keep only findings that name a section we actually wrote."""
    out: List[Dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("section_id") or "").strip().strip("[]")
        detail = str(item.get("detail") or "").strip()
        if sid not in sections or not detail:
            continue
        kind = str(item.get("kind") or "other").lower()
        out.append(
            {
                "section_id": sid,
                "severity": SEV_MAJOR if str(item.get("severity")) == "major" else SEV_MINOR,
                "kind": kind if kind in LLM_KINDS else "other",
                "detail": detail[:400],
                "fix": str(item.get("fix") or "").strip()[:300],
            }
        )
    return out[:12]


def merge_llm_findings(vr: VerifyReport, review: Dict[str, Any]) -> List[Finding]:
    """Fold the reviewer's findings into the rule report, and return them.

    The caller keeps the returned list because the rule findings are recomputed
    from the final text at the end of the stage, while these are a read of a
    specific draft and have to be carried forward deliberately.
    """
    added: List[Finding] = []
    for f in review.get("findings") or []:
        finding = Finding(
            section_id=f["section_id"],
            severity=f["severity"],
            kind=f["kind"],
            detail=f["detail"],
            fix=f.get("fix", ""),
        )
        vr.add(finding)
        added.append(finding)
    return added


# ── Rewrite routing ───────────────────────────────────────────────────────────
def rewrite_directive(findings: Sequence[Finding]) -> str:
    """The correction brief handed back to the writer for one section."""
    lines = []
    for f in findings:
        line = f"- [{f.severity}] {f.detail}"
        if f.fix:
            line += f"\n  Required fix: {f.fix}"
        lines.append(line)
    return "\n".join(lines)


def sections_to_rewrite(
    vr: VerifyReport, *, rewritable: Set[str], limit: int = 4
) -> List[Tuple[str, List[Finding]]]:
    """Pick the sections worth spending a rewrite call on, worst first.

    One major defect earns a rewrite on its own; minor ones need to arrive in
    pairs, because a single soft finding is not worth a model call and a
    regenerated section is not automatically a better one.
    """
    groups: Dict[str, List[Finding]] = {}
    for f in vr.open:
        if f.severity == SEV_COSMETIC or f.section_id not in rewritable:
            continue
        groups.setdefault(f.section_id, []).append(f)

    ranked = [
        (score_findings(fs), sid, fs)
        for sid, fs in groups.items()
        if any(f.severity == SEV_MAJOR for f in fs) or len(fs) >= 2
    ]
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [(sid, fs) for _, sid, fs in ranked[:limit]]


def verdict_of(vr: VerifyReport, review: Dict[str, Any]) -> str:
    """Final verdict after the rewrite budget is spent.

    `pass` — nothing outstanding. `revised` — defects were found and dealt with.
    `flagged` — major defects survived the rewrites and the reader is told so,
    which is the honest outcome when the budget runs out mid-problem.
    """
    if vr.majors:
        return "flagged"
    if vr.findings or (review.get("findings") or []):
        return "revised"
    return "pass"
