# Analysts and protocol

## The idea

Vantage models competitive research as a focused consulting team. Twelve active
analysts are defined in [`backend/app/data/experts.json`](../backend/app/data/experts.json),
alongside 40 archived identities retained for historical reports. Twenty-eight
industry modules in `backend/app/data/industry_modules.json` supply reusable
research methods without acting as additional analysts.

Each active role has structured `work_instructions`: responsibilities,
preferred sources, checks, deliverables and limits. Display biographies are
separate from execution prompts. Both individual and team prompts carry these
instructions. Industry modules add public source preferences, interpretation
checks and search directions to analysis, review, writing and rework.

Generated content uses American English. The U.S. market is the default when no
market is specified; explicit user selections take precedence. Source preferences
never imply access to paid databases, private interviews or unavailable tools.

Every persona block ends with the same guard — *your background shapes which
sources you reach for and what you interrogate; it never licenses a claim the
evidence below does not support*. An analyst identity is there to direct
attention, never to supply facts from the model's own memory.

## Tiers

| Tier | Count | Group | Responsibility |
|---|---|---|---|
| **L3 · Decision** | 3 | `decision` | Scope the brief, assemble the team, adjudicate quality, sign off |
| **L2 · Strategy** | 7 | `strategy` | Competitive strategy, pricing, user research, finance, product and technology, go-to-market, compliance |
| **L1 · Specialist** | 2 | `function` | Public evidence collection and user feedback |

### The decision tier

| ID | Name | Role |
|---|---|---|
| L3-001 | Eleanor Vance | Chief Research Director — decomposes the brief, assembles the team, signs off |
| L3-002 | Marcus Chen | Chief Analyst Officer — owns analytical rigor and authorship |
| L3-003 | Priya Raghavan | Chief Quality Officer — devil's advocate, drives fact-checking and rework |

### Core roles and merged methods

The seven strategy roles retain IDs L2-001, L2-002, L2-003, L2-005, L2-006,
L2-007 and L2-009. Competitive strategy absorbs public competitor signals;
finance absorbs public filing research; user research absorbs published
qualitative accounts. The quality officer owns factual and statistical checks,
including survey methodology. Evidence collection (L1-025) and user feedback
(L1-030) are fixed responsibilities; feedback combines review mining and
community listening.

### Industry modules

**Coverage (28):** financial services, SaaS, robotics, semiconductors,
healthcare, energy and EV, cloud, AI and foundation models, retail, gaming,
blockchain, media, logistics, restaurants, beauty, real estate, education,
apparel, agriculture, travel, insurance, sustainability, aerospace, consumer
hardware, cybersecurity and identity, telecom, HR tech, legal and govtech.

Modules are selected after Understand identifies the category. English lexical
scoring ranks positive matches, breaking ties by module ID; at most two are
loaded. Generic requests for pricing or reviews do not identify an industry.
Up to two module search directions fit inside the mode's existing angle budget,
with a recency direction retained when present. Product selections remain
authoritative. Module snapshots are persisted in reports and reused for later
refinement, independently of subsequent catalog edits.

## Staffing

Five roles are permanent: director, chief analyst, quality officer, evidence
collection and user feedback. Only strategy analysts are selected per brief:

1. **Score.** Active profiles are scored against the brief on lexical overlap with
   its `knowledge_tags`, `skills` and `role_title`. Deterministic and free.
2. **Shortlist.** The seven active strategy roles are offered to the existing
   dispatch call with their work instructions and loaded industry methods.
   Each selected role gets a reason specifying its task and relevance.
3. **Normalize.** `normalize_team` repairs the result: unknown and duplicate ids
   and archived IDs dropped, mode bounds enforced, and all five fixed roles
   guaranteed. Invalid or failed selections are filled by deterministic
   relevance ranking to the mode's minimum strategy count.

| Mode | Strategy analysts | Total analysts |
|---|---|---|
| Quick | 1–2 | 6–7 |
| Deep | 2–3 | 7–8 |
| Expert | 3–4 | 8–9 |

Mock applies these same bounds without inventing analytical conclusions.
Modules do not contribute to analyst counts or workload statistics. No separate
per-analyst inference rounds are added.

## Role to stage

Fixed responsibilities have explicit owners; strategy analysis is matched to
the brief's focus areas.

| Stage | Assignment |
|---|---|
| intake / orchestrator / done | The director (L3-001) |
| collect | Evidence Collection Specialist (L1-025) |
| sentiment | User Feedback Specialist (L1-030) |
| analyze | The strategy advisor whose specialism best fits the brief's focus areas |
| audit / verify | The quality officer (L3-003) |
| write | The validated writing plan assigns each demand-driven chapter to an actual staffed analyst; assignment follows chapter goals and role expertise, rather than fixed section IDs. |

Section authorship is not cosmetic. Each section carries its assigned analyst's
persona, so different sections are argued from different expertise, and a
rewrite ordered by the verify stage goes back to whoever wrote it. Dependencies
use completed predecessor arguments. Independent chapters may run concurrently;
planned summaries and recommendations follow the body and refresh after relevant
body repair. All authors share factual conditions, unknowns and the same source
constraints. The quality officer checks complete prose and independently extracted
judgments against saved sources before a real report can be delivered.

## Catalog compatibility

`GET /api/experts` returns the 12 active profiles; `include_archived=true`
returns all 52 identities. Expert details resolve archived IDs, and workload
supports the same filter without merging or deleting historical statistics.
`GET /api/industry-modules` returns the separate module catalog.

The frontend indexes all identities but lists only core analysts by default.
Industry Modules is a separate searchable view, and historical analyst pages
show an archived marker. Both catalogs ship as offline assets. Old reports
without `industry_modules` remain readable and refinable; no database migration
or historical report rewrite is required.

## Message protocol

Agents hand off through a typed `Envelope`
([`models.py`](../backend/app/core/models.py)) rather than free text, so a
request names its receiver and carries specific issues instead of a paragraph
the next stage has to interpret:

```python
@dataclass
class Envelope:
    msg_id: str
    sender: str        # agent id
    receiver: str      # agent id or pipeline stage
    task_type: str     # PRODUCE | REWORK | PASS
    payload: dict
    issues: list       # Issue records from the quality review
    trace_ref: str
```

```python
@dataclass
class Issue:
    issue_id: str
    target: str        # claim id, "brand:X", "dimension:Y", or "schema"
    severity: str      # high | medium | low
    reason: str
    raised_by: str     # agent id
```

Rework routes by cause: insufficient evidence sends a `REWORK` envelope to
`collect`, followed by `analyze`; analysis defects send one to `analyze` directly.
Both main and structured analysis receive the latest issue-specific instructions.
Each round includes a new evidence-aware review. Quick, Deep and Expert allow
2, 3 and 5 repair rounds respectively, excluding the initial review. Serious
issues remaining after the cap block writing; unavailable model review also
blocks writing. Saved task research remains readable without a finished report.
`issues_resolved` counts confirmed issue closures, not score improvements.

## Evidence and claims

Each collected source carries a computed credibility score
([`credibility.py`](../backend/app/core/credibility.py)):

```
evidence_id · source_url · source_type · title · excerpt · captured_at
credibility(0-100) · collected_by · brand · domain · freshness_days
```

`source_type` covers `official`, `sec_filing`, `analyst`, `news`, `review`,
`reddit`, `hackernews`, `youtube`, `x`, `forum`, `web`.

Every claim carries evidence, and confidence follows from the sourcing rather
than from the model's own assessment:

| Condition | Confidence |
|---|---|
| No evidence at all | `unverified` |
| ≥2 **independent domains** | `high` |
| ≥2 citations from one domain | `medium` |
| A single citation | `low` |

## The four rules

1. **No claim without evidence.** Every conclusion carries evidence IDs or is
   marked `unverified`. Citations the model invents are filtered against the
   real evidence set before they can reach the page
   ([`schemas._filter_eids`](../backend/app/core/schemas.py)), so a fabricated
   source cannot make a claim look supported.

2. **Cross-validation.** High confidence requires independent sources; sibling
   domains and near copies do not count separately. A single verified original
   official source can support a published fact passing audit without upgrading
   its confidence. Critical comparisons and inferences require independent support.

3. **Rework closes the loop.** When quality falls short, work goes back to
   collection or analysis. The bar does not move to accommodate a weak result.
   The reviewer can trigger this on judgement alone, even when the rules pass.

4. **Observability.** Every model call records its prompt, output, token cost,
   latency, decision and linked evidence. Queryable during the run, replayable
   afterward.

These are the engineering expression of the product's claim: every conclusion
carries its source.

## Collection ethics

Collection uses public sources only. The fetcher blocks private/local source addresses, validates redirects, limits
response bodies, pins connections to checked public addresses, and applies a
per-domain delay. It uses a browser-style user agent. Automatic `robots.txt`
checking is not implemented; callers must review source policies before collection. No credentialed scraping, no pretexting, no circumventing paywalls —
consistent with SCIP's practice standards, which the competitive-intelligence
lead's profile reflects.
