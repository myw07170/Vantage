# Architecture

## Three pieces

| Directory | Role |
|---|---|
| `frontend/` | React 19 SPA. Talks to the backend over REST plus one SSE stream. |
| `backend/` | FastAPI. Orchestration, collection, model calls, credibility scoring, trace, SQLite. |
| `scripts/` | Smoke tests and the headless pipeline harness. |

Unlike the project this derives from, there is no duplicated serverless mirror of
the backend — one copy, run directly.

## Data flow

```
Browser
  ├── REST  ──────────────►  FastAPI (main.py)
  └── EventSource ────────►  GET /api/tasks/{id}/stream
                                    │
                                    ▼
                            orchestrator.run_pipeline()
                                    │
        ┌───────────────┬───────────┼───────────┬───────────────┐
        ▼               ▼           ▼           ▼               ▼
    llm.py          search/     fetcher.py  credibility.py   trace.py
   (Gemini)      (Exa/Tavily/    (httpx +     (0-100 score)  (span buffer)
        │            DDG)       trafilatura)                      │
        ▼               │                                         │
   ratelimit.py         │                                         │
  (token buckets)       ▼                                         ▼
                   the open web                            SQLite (db.py)
```

Every synchronous step runs inside `asyncio.to_thread`, so the SSE generator
never blocks while a page is being fetched or a model is thinking.

## Core modules

| Module | Responsibility |
|---|---|
| `orchestrator.py` | The pipeline. One async generator that yields SSE events as it walks the stages. |
| `llm.py` | Gemini wrapper: `chat`, `chat_json`, `chat_schema`. Native JSON mode, token accounting, trace hook. |
| `ratelimit.py` | Thread-safe RPM/RPD/TPM token buckets plus a concurrency semaphore. |
| `search/` | Provider protocol and adapters, with failover and relevance filtering. |
| `fetcher.py` | Page fetch and article extraction, with per-domain politeness and an in-process cache. |
| `platforms.py` | Social platform registry. Reddit and HN have API collectors; the rest use site-restricted search. |
| `sentiment.py` | Sentiment classification, opinion camps, representative quotes. |
| `credibility.py` | Deterministic 0-100 evidence scoring. No model involved. |
| `audit.py` | Quality evaluation, the LLM reviewer, and rework routing. |
| `verify.py` | Post-write checks on the finished document: citation validation, formatting repair, editorial review, rewrite routing. |
| `schemas.py` | Tolerant coercion into feature tree / pricing / persona, with citation filtering. |
| `metrics.py` | Impact metrics, each with its formula. |
| `charts.py` | ECharts option builders. |
| `trace.py` | Contextvar-based span recording. |
| `db.py` | SQLite: 7 tables, thread-local connections, WAL. |

## The pipeline

```
intake → orchestrator → collect → analyze → audit ──pass──► write → verify → done
                          ▲                    │                      │
                          └──────rework────────┘                      │
                                                  section rewrite ◄───┘
```

Note that **audit runs before write**. Rework improves the analysis that gets
written up, rather than rewriting prose around unchanged findings. **Verify runs
after write**, on the document itself — the two gates answer different
questions, and neither can answer the other's.

| Stage | What happens |
|---|---|
| **intake** | The director breaks the brief into competitors, focus areas and search angles. |
| **orchestrator** | A team is selected from the 48-analyst roster, each with a stated reason. |
| **collect** | Per competitor: multi-angle search → fetch → relevance filter → `Evidence` with a credibility score. Then user voice across every registered platform. |
| **analyze** | Cross-validation into claims, plus the structured feature/pricing/persona objects. Sentiment is classified here. |
| **audit** | Rule-based quality evaluation plus a model review that scores each dimension. Either passes or emits `REWORK` envelopes. |
| **write** | Sections written in parallel, paced by the rate limiter. Charts built from real analysis output. |
| **verify** | The finished prose is checked and repaired, then read as a whole for contradictions and unsupported claims. Failing sections are rewritten. |
| **done** | Metrics computed, report assembled and persisted, traces saved, analyst stats updated. |

### Research modes

`MODE_CONFIG` in `orchestrator.py` scales everything together:

| | Quick | Deep | Expert |
|---|---|---|---|
| Search angles | 4 | 6 | 9 |
| Pages fetched per brand | 6 | 12 | 16 |
| Sections | 5 | 9 | 12 |
| Rework rounds | 0 | 1 | 2 |
| Min paragraphs/section | 3 | 5 | 7 |
| Verify rounds | 1 | 1 | 2 |
| Max section rewrites | 2 | 4 | 6 |

### Rework

`audit.decide_rework()` routes by cause, which is what makes the loop converge
instead of re-running everything:

- thin evidence for a brand → back to **collect** with extra angles
- an uncovered dimension or an empty schema → back to **analyze**, with the
  reviewer's specific findings injected into the prompt

After the loop, a second review runs. Improvement is measured as the maximum of
three signals — rule-issue delta, reviewer-issue delta, and the number of score
dimensions that went up — because the reviewer regenerates its issue list each
round, which makes raw counts noisy.

### Verification

`verify.py` gates the artifact rather than the analysis, in two layers.

**Rules, applied and repaired in code.** Every `[e_xxxx]` marker in the prose is
resolved against the collected evidence: real ids are normalized and collected
per section, ids matching nothing are removed. Leftover markdown, literal `\n`,
doubled spacing and stray asterisks are stripped. Truncated paragraphs, the
writer's failure placeholder, empty sections, duplicated paragraphs and
impossible shares (a percentage over 100 in share context — growth rates are
left alone) are recorded as findings.

**A single editorial read.** One model call sees every section at once — the
only stage that does — and looks for contradictions between sections,
quantitative assertions with nothing behind them, hedged claims restated as
fact, and repetition.

**Remediation is rewriting, never rework.** Nothing goes back to collection or
analysis: a section with one major finding, or two minor ones, is rewritten
against the same evidence with its own defects named in the prompt. The new
draft is re-checked and kept only if it is not mechanically worse than the one
it replaces, so a regeneration cannot quietly degrade the report. Anything still
open when the rewrite budget runs out ships as a visible `flagged` verdict with
the findings listed — the report says what is wrong with it rather than hiding
it.

The sentiment section is checked but never rewritten: it is written from the
computed sentiment table, so its figures are sourced by construction and it
carries no inline citations by design.

## Model routing

Gemini's free tier has no Pro model, so `_model(tier)` collapses to two:

| Tier | Model | Used for |
|---|---|---|
| `core` / `aux` | `gemini-3.5-flash` | Sections, cross-analysis, audit review |
| `fast` | `gemini-3.5-flash-lite` | Intake, scope discovery, dispatch, sentiment classification |

Rate-limit buckets are per tier, and the fast tier only gets its own budget when
it is genuinely a different model.

## Evidence and claims

```
Evidence:  evidence_id · source_url · source_type · title · excerpt
           captured_at · credibility(0-100) · collected_by · brand
           domain · freshness_days
```

`source_type` is defined once in `models.py` and imported everywhere:
`official · sec_filing · analyst · news · review · reddit · hackernews ·
youtube · x · forum · web`.

Confidence is assigned by rule in `make_claim()`:

| Condition | Confidence |
|---|---|
| No evidence | `unverified` |
| ≥2 independent domains | `high` |
| ≥2 citations, same domain | `medium` |
| 1 citation | `low` |

## Observability

`trace.set_context()` writes a contextvar before each `asyncio.to_thread` hop.
Because `to_thread` copies the context, the synchronous `llm.chat()` running in
that worker sees it and records a span with the right agent and stage attached —
no call site has to pass it.

Spans are drained incrementally at each stage boundary and pushed over SSE, then
persisted with the report for the decision-replay view.

## SSE

`GET /api/tasks/{id}/stream` **starts** the research; it is not idempotent.
Each event carries a monotonic `id:`, and the client de-duplicates on it so a
browser reconnect does not double up the thought stream. The client caps
reconnection attempts, because unbounded retry against a non-idempotent endpoint
would launch duplicate runs.

Event types: `node_update`, `thought`, `message`, `evidence`, `chart`, `image`,
`progress`, `trace`, `report_ready`, `done`, `error`.

## Storage

SQLite with thread-local connections (a shared connection across `to_thread`
workers deadlocks), WAL mode and a 30-second busy timeout.

Tables: `tasks`, `reports`, `evidences`, `subscriptions`, `expert_stats`,
`traces`, `report_feedback` — with indexes on every hot filter path.
