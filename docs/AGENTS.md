# Analysts and protocol

## The idea

Vantage models competitive research as a consulting team at work. 48 analysts are
defined in [`backend/app/data/experts.json`](../backend/app/data/experts.json),
organized in three tiers. Each engagement gets a team picked for the brief:
the decision tier scopes and signs off, the strategy and specialist tiers do the
analysis and collection.

These are role definitions with real domain grounding — an analyst's
`knowledge_base` names the actual sources they work from (SEC EDGAR, STR, FDA
510(k), Circana, USAspending) — and that framing shapes what the model looks for
and how it reasons. They are prompt personas and trace labels, not 48 separate
code paths.

## Tiers

| Tier | Count | Group | Responsibility |
|---|---|---|---|
| **L3 · Decision** | 3 | `decision` | Scope the brief, assemble the team, adjudicate quality, sign off |
| **L2 · Strategy** | 9 | `strategy` | Strategy, pricing, user research, competitive intel, finance, architecture, marketing, data, compliance |
| **L1 · Specialist** | 36 | `industry` (24) + `function` (12) | Industry depth and research tradecraft |

### The decision tier

| ID | Name | Role |
|---|---|---|
| L3-001 | Eleanor Vance | Chief Research Director — decomposes the brief, assembles the team, signs off |
| L3-002 | Marcus Chen | Chief Analyst Officer — owns analytical rigor and authorship |
| L3-003 | Priya Raghavan | Chief Quality Officer — devil's advocate, drives fact-checking and rework |

### Specialists

**Industry (24):** financial services, SaaS, robotics, semiconductors,
healthcare, energy and EV, cloud, AI and foundation models, retail, gaming,
blockchain, media, logistics, restaurants, beauty, real estate, education,
apparel, agriculture, travel, insurance, sustainability, aerospace, consumer
hardware.

**Function (12):** web collection, fact-checking, international research, survey
methodology, user interviews, social listening, review mining, patents, hiring
intelligence, public filings, data visualization, archiving.

## Role to stage

| Stage | Tier | Assignment |
|---|---|---|
| intake / orchestrator | L3 | The director |
| collect | L1 | First specialist on the team; social listening goes to a `function` analyst |
| analyze | L2 | First strategy advisor |
| audit | L3 | The quality officer (L3-003) |
| write | L2 + L1 | The chief analyst, or the lead |
| done | L3 | The director |

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
`collect`; a missing dimension or empty schema sends one to `analyze`. Each
round recomputes quality and records `issues_resolved` alongside the before and
after metrics.

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

2. **Cross-validation.** High confidence requires two or more independent
   domains. Two citations from the same site is corroboration, not verification.

3. **Rework closes the loop.** When quality falls short, work goes back to
   collection or analysis. The bar does not move to accommodate a weak result.
   The reviewer can trigger this on judgement alone, even when the rules pass.

4. **Observability.** Every model call records its prompt, output, token cost,
   latency, decision and linked evidence. Queryable during the run, replayable
   afterward.

These are the engineering expression of the product's claim: every conclusion
carries its source.

## Collection ethics

Collection uses public sources only. The fetcher honours `robots.txt`
conventions, applies a per-domain delay, and identifies itself with a normal
user agent. No credentialed scraping, no pretexting, no circumventing paywalls —
consistent with SCIP's practice standards, which the competitive-intelligence
lead's profile reflects.
