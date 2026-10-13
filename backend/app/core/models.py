"""Core data models: Evidence, Claim, Issue, Envelope.

`SourceType` is the single definition of the evidence taxonomy. It is imported
by credibility scoring, the orchestrator's URL classifier and the frontend's
label maps — declaring it once keeps those three in sync.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


class SourceType:
    """Where a piece of evidence came from. Drives base credibility scoring."""

    OFFICIAL = "official"          # the vendor's own site, docs, changelog
    SEC_FILING = "sec_filing"      # 10-K/10-Q/S-1, investor relations
    ANALYST = "analyst"            # Gartner, Forrester, CB Insights, PitchBook
    NEWS = "news"                  # press and trade publications
    REVIEW = "review"              # G2, Trustpilot, Capterra
    REDDIT = "reddit"
    HACKERNEWS = "hackernews"
    YOUTUBE = "youtube"
    X = "x"                        # X / Twitter
    FORUM = "forum"                # Stack Overflow, Discourse, product forums
    WEB = "web"                    # anything else that parsed
    UNKNOWN = "unknown"

    ALL = (
        OFFICIAL, SEC_FILING, ANALYST, NEWS, REVIEW, REDDIT,
        HACKERNEWS, YOUTUBE, X, FORUM, WEB, UNKNOWN,
    )

    #: Types that represent user voice rather than institutional publishing.
    SOCIAL = (REDDIT, HACKERNEWS, YOUTUBE, X, REVIEW, FORUM)


@dataclass
class Evidence:
    evidence_id: str
    source_url: str
    source_type: str  # one of SourceType.ALL
    title: str
    excerpt: str
    captured_at: str
    credibility: float  # 0-100, computed by credibility.score_evidence
    collected_by: str
    screenshot_path: str = ""
    image_urls: List[str] = field(default_factory=list)
    lang: str = "en"
    brand: str = ""
    domain: str = ""
    freshness_days: Optional[int] = None  # days since publication; None if unparseable

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Claim:
    claim_id: str
    text: str
    field: str  # feature_tree|pricing_model|user_persona|swot|sentiment|overview
    evidence_ids: List[str]
    confidence: str  # high|medium|low|unverified
    cross_validated: bool
    author: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Issue:
    issue_id: str
    target: str  # a claim_id or a section id
    severity: str  # high|medium|low
    reason: str
    raised_by: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Envelope:
    """Structured message passed between agents.

    Using a typed envelope rather than free text keeps hand-offs unambiguous —
    the quality officer's rework request names its receiver and carries the
    specific issues, instead of a paragraph the next agent has to interpret.
    """

    msg_id: str
    sender: str
    receiver: str
    task_type: str  # PRODUCE | REWORK | PASS
    payload: Dict[str, Any] = field(default_factory=dict)
    issues: List[Dict[str, Any]] = field(default_factory=list)
    trace_ref: str = ""


def make_claim(
    claim_id: str,
    text: str,
    field_name: str,
    evidence_ids: List[str],
    author: str,
    independent_domains: int = 0,
) -> Claim:
    """Assign confidence by rule — this encodes two of the four iron rules.

    No evidence means `unverified`, never a quiet assertion. Two or more
    *independent domains* is the only path to `high`; two citations from the
    same site is corroboration, not cross-validation.
    """
    if not evidence_ids:
        return Claim(claim_id, text, field_name, [], "unverified", False, author)
    cross = independent_domains >= 2
    if cross:
        conf = "high"
    elif len(evidence_ids) >= 2:
        conf = "medium"
    else:
        conf = "low"
    return Claim(claim_id, text, field_name, evidence_ids, conf, cross, author)
