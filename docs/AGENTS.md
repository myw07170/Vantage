# Three fixed research roles

| Role | Responsibility | Handoff |
|---|---|---|
| Collector | Focused search, public fetching, identity, attribution, excerpts and dates | Evidence and source limitations |
| Analyst | Atomic comparisons, conditional judgments, short brief and changes | Draft, citations and dependencies |
| Reviewer | Validity, semantic support, conditions, dates, conflicts and gaps | Individual states and concrete issues |

Roles share the locally configured core model, with independent calls and
responsibility prompts in backend/app/core/roles.py. Source text is untrusted
data, never execution instructions. Roles cannot supply facts from model memory.
External identity checks must cite locatable text.

Before research, Collector also prepares a concise understanding summary,
prefilled product/topic proposals and a choice questionnaire. This is a separate
explicit background operation using the same core model and its own cumulative
12,000-token / 120-second execution budget. User answer time is excluded. Named
products are constrained to the request, answers and explicit edits; a matching
public website is a proposal for user ownership confirmation, not established
official identity. Failed checks remain visible. Preparation prompts live in
backend/app/core/preparation.py. No private reasoning is displayed.

Review does not use source/domain counts or an overall score as proof. One
applicable vendor page can suffice. Ungrounded reviewer assessments remain
Pending review. Compound claims must be split; unresolved dependencies cannot
support a recommendation.

Rules check evidence IDs, quote location, product ownership, pricing conditions
and change dates. Semantic calls assess complete statements against actual
evidence. At most two targeted reworks carry affected IDs and concrete issues;
scope is never expanded. Budgets preserve unresolved work rather than passing it.

Mock follows the same three roles, copies provided excerpts and reports Unknown
semantic support. It never invents prices, charts, personas or recommendations.
Mock provenance remains visible in saved versions.
