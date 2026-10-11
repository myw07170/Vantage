"""Version-two contracts shared by research, persistence and the API."""
from __future__ import annotations
import datetime as dt
from typing import Any, Literal
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()

class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class Product(Contract):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=150)
    website: str = Field(min_length=1, max_length=2000)
    category: str = Field(min_length=1, max_length=200)
    own_product: bool = False
    confirmed: Literal[True]

    @field_validator("website")
    @classmethod
    def website_url(cls, value: str) -> str:
        u = urlparse(value)
        if u.scheme not in ("https", "http") or not u.hostname or u.username or u.password:
            raise ValueError("Provide the product's public HTTP(S) website.")
        return value.rstrip("/")

    @field_validator("name")
    @classmethod
    def independent_product(cls, value: str) -> str:
        if any(token in value.lower() for token in (" vs ", " versus ", " / ", " + ")):
            raise ValueError("Use a separate card for each independent product.")
        return value

class Topic(Contract):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    focus: list[str] = Field(default_factory=list)

    @field_validator("focus")
    @classmethod
    def focus_points(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 1000 for v in values):
            raise ValueError("Focus points must be nonempty and at most 1,000 characters.")
        return list(dict.fromkeys(v.strip() for v in values))

DEFAULT_TOPICS = [
    {"id": "features", "name": "Features and limitations", "focus": []},
    {"id": "pricing", "name": "Plans and billing", "focus": []},
    {"id": "positioning", "name": "Audience and positioning", "focus": []},
]

class ResearchScope(Contract):
    products: list[Product] = Field(min_length=1, max_length=4)
    topics: list[Topic] = Field(min_length=1)
    changes_days: Literal[90] = 90
    scope_acknowledged: bool = False
    limitations: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def identity_and_scope(self):
        for values, label in (([p.id for p in self.products], "product IDs"),
                              ([p.name.casefold() for p in self.products], "product names"),
                              ([p.website.casefold() for p in self.products], "product websites"),
                              ([t.id for t in self.topics], "topic IDs")):
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate {label}; resolve the product identities and scope.")
        if sum(p.own_product for p in self.products) > 1:
            raise ValueError("Mark at most one product as your own.")
        if self.warnings() and not self.scope_acknowledged:
            raise ValueError("Confirm the scope warnings before starting: " + " ".join(self.warnings()))
        strategic = ("swot", "five forces", "market share", "growth", "sentiment", "persona", "forecast")
        if any(s in (t.name + " " + " ".join(t.focus)).lower() for t in self.topics for s in strategic):
            if not self.limitations:
                raise ValueError("Describe the strategic question boundaries in Scope notes.")
        return self

    def warnings(self) -> list[str]:
        messages = []
        if len(self.topics) > 6 or sum(max(1, len(t.focus)) for t in self.topics) * len(self.products) > 24:
            messages.append("This scope may exceed the usual 5–8 minute target. Consider splitting it.")
        strategic = ("swot", "five forces", "market share", "growth", "sentiment", "persona", "forecast")
        if any(s in (t.name + " " + " ".join(t.focus)).lower() for t in self.topics for s in strategic):
            messages.append("Strategic or broad topics require a bounded question; public evidence may be insufficient.")
        return messages

class Citation(Contract):
    evidence_id: str
    quote: str = Field(min_length=1)

ReviewStatus = Literal["supported", "unknown", "conflicting", "pending_review"]

class Review(Contract):
    status: ReviewStatus = "pending_review"
    citation_valid: bool | None = None
    support_checked: bool = False
    reason: str = "Not yet reviewed."
    evidence_ids: list[str] = Field(default_factory=list)
    quotes: list[Citation] = Field(default_factory=list)
    checked_at: str | None = None

class ReportItem(Contract):
    id: str = Field(min_length=1)
    kind: Literal["fact", "inference", "change"] = "fact"
    product_id: str = ""
    topic_id: str = ""
    text: str = Field(min_length=1)
    citations: list[Citation] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)
    effective_date: str | None = None
    review: Review = Field(default_factory=Review)

class Evidence(Contract):
    evidence_id: str
    product_id: str
    topic_id: str = ""
    source_url: str
    source_type: Literal["official", "external", "unknown"] = "unknown"
    attribution: str = ""
    title: str = ""
    excerpt: str
    context: str
    captured_at: str
    published_at: str | None = None
    published_date_basis: str = ""
    degraded: bool = False
    limitation: str = ""

class ReportContent(Contract):
    products: list[Product]
    topics: list[Topic]
    checked_at: str
    changes_since: str
    comparison: list[ReportItem] = Field(default_factory=list)
    brief: list[ReportItem] = Field(default_factory=list)
    changes: list[ReportItem] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    charts: list[dict] = Field(default_factory=list)
    review_summary: dict = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    is_mock: bool = False
    llm_provider: str = ""

def all_items(content: dict) -> list[dict]:
    return [item for section in ("comparison", "brief", "changes") for item in content.get(section, [])]
