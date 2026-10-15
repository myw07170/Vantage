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
   (providers)   (Exa/Tavily/    (httpx +     (0-100 score)  (span buffer)
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
| `tasks.py` | Runs each task once, retains live events for subscribers, persists terminal state. |
| `orchestrator.py` | The pipeline. One async generator that yields SSE events as it walks the stages. |
| `llm.py` | Provider-neutral `chat`, `chat_json`, `chat_schema`: HTTP completions, JSON mode, retries, token accounting, trace hook. |
| `llm_mock.py` | Deterministic model substitute using explicit task kinds and input context; no model network, fabricated prices or citations. |
| `ratelimit.py` | Thread-safe RPM/RPD/TPM token buckets plus a concurrency semaphore. |
| `search/` | Provider protocol and adapters, with failover and relevance filtering. |
| `fetcher.py` | Page fetch and article extraction, with per-domain politeness and an in-process cache. |
| `platforms.py` | Social platform registry. Reddit and HN have API collectors; the rest use site-restricted search. |
| `sentiment.py` | Sentiment classification, opinion camps, representative quotes. |
| `credibility.py` | Deterministic 0-100 evidence scoring. No model involved. |
| `audit.py` | Quality evaluation, the LLM reviewer, and rework routing. |
| `writing.py` | Demand-driven planning, complete material indexing, dependency groups, source-linked chapter writing and editorial integration. |
| `written_review.py` | Independent assertion extraction from complete prose, original-source checks and cross-chapter consistency review. |
| `verify.py` | Mechanical citation/format checks, full-document review routing and bounded chapter repair. |
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
| **intake** | The director plans research for the confirmed products, focus and category. Up to two matching industry modules contribute search directions within the existing budget. |
| **orchestrator** | Five fixed core responsibilities plus mode-specific strategy analysts are staffed from the 12-role catalog. Each role has stated ownership; industry modules are shown separately. |
| **collect** | Per competitor: multi-angle search → fetch → relevance filter → `Evidence` with a credibility score. Then user voice across every registered platform. |
| **analyze** | Cross-validation into claims, plus the structured feature/pricing/persona objects. Sentiment is classified here. |
| **audit** | Rule-based quality evaluation plus a model review that scores each dimension. Either passes or emits `REWORK` envelopes. |
| **write** | Validated user-specific outline → dependency groups → source-linked chapters → editorial integration → refreshed final summary/advice when planned. Independent chapters run in parallel. |
| **verify** | The finished prose is checked and repaired, then read as a whole for contradictions and unsupported claims. Failing sections are rewritten. |
| **done** | Metrics computed, report assembled and persisted, traces saved, analyst stats updated. |

### Research modes

`MODE_CONFIG` in `orchestrator.py` scales everything together:

| | Quick | Deep | Expert |
|---|---|---|---|
| Search angles | 4 | 6 | 9 |
| Strategy analysts | 1–2 | 2–3 | 3–4 |
| Total analysts | 6–7 | 7–8 | 8–9 |
| Pages fetched per brand | 6 | 12 | 16 |
| Default English word target (elastic) | ~1,500 | ~4,000 | ~8,000 |
| Rework rounds | 2 | 3 | 5 |
| Outline / paragraph floor | Dynamic / none | Dynamic / none | Dynamic / none |
| Verify rounds | 1 | 1 | 2 |
| Max section rewrites | 2 | 4 | 6 |

The catalog retains all original IDs for historical references, with 12 active
roles and 40 archived profiles. `/api/experts` defaults to active roles;
`include_archived=true` includes historical identities. Workload follows the
same filter without rewriting stored statistics. `/api/industry-modules` exposes
28 reusable methods with sources, checks and search angles.

Module matching uses English lexical scoring and deterministic ID tie-breaking;
generic research dimensions alone do not identify an industry. At most two
positive matches are loaded, or none when no industry signal is present. Module
snapshots are carried on the team event and saved in the report's
`industry_modules` field. Analysis, review, writing, rework and later refinement
use those methods; older reports without the field use an empty module list.
No extra model calls or database migrations are introduced. Generated prose uses
American English, with the U.S. as the default market and explicit user markets
taking precedence.

### Rework

The initial audit does not consume a repair round. Each repair round performs
targeted collection when needed, then one unified analysis pass (claims and
structured data), followed by another evidence-aware model review. Both analysis
calls receive the latest issues and fixes. Collection-only repairs also re-analyze,
including when no new source was found. Every affected brand is eligible; the
mode's existing per-brand angle/page budgets still apply each round.

All evidence reaches analysis in bounded packets, balanced across brands with new
and repair-related material first. Citations are restricted to the packet actually
provided. The gate reviews every claim, structured assertion and chart dataset,
plus a brand-by-requested-dimension checklist. Review packets include relevant
passages from saved text and distinguish body text, snippets and comments. The
fetcher still retains at most 4,000 characters per webpage; this is not a claim to
have read the entire original source.

A published fact may use one verified original official source. Critical
comparisons/inferences need two independent sources; sibling subdomains and near
copies do not establish independence. URL source-type heuristics alone do not
establish official ownership. Scores are informative, never a substitute for
resolving an issue. Stable issue IDs track confirmed corrections, removals,
declared unknowns, open issues and newly found issues.

Unknown/undisclosed information can satisfy a requested dimension only with
successful targeted search provenance or a reviewed non-disclosure source. Tool
failures do not prove absence. Unknowns cannot justify scores, rankings or
recommendations. Unsupported optional schemas need not be filled merely to make
the report look complete.

The gate stops early on approval. After the repair cap, unresolved serious issues
block writing; minor issues may ship as explicit warnings. Model failure or
incomplete review output stops writing instead of falling back to approval.
Mock remains an explicitly labelled simulation, without semantic verification.

Before audit and after each round, task research is saved in the additive
`tasks.audit_data` JSON column. `GET /api/tasks/{id}/audit` returns the saved
evidence text, analysis, structured data, sentiment, query outcomes, round history
and trace. Task details expose an optional `auditSummary`. Blocked/unavailable
tasks retain the existing `failed` status and emit `audit_blocked` or
`audit_unavailable`; no report is created. Refresh restores the research viewer.
Successful reports keep the existing `audit_review.before/after` fields and add
history, final status, issue outcomes, coverage and unknowns. SSE analysis snapshots
replace earlier claims. There is no automatic resume or gate override.

### Demand-driven writing

After audit passes, `writing_plan` chooses the title, chapter count, ordering,
answer goals, authors from the staffed team, dependencies, source assignments,
word targets and typed components. It sees the confirmed purpose, audience,
focus, market and constraints. SWOT, five forces, moat, sentiment, summary,
recommendations and appendices are optional; focus coverage does not require a
chapter per dimension. Explicit user length takes precedence over mode defaults.
Thin evidence is a reason for concise writing, not padding.

All saved evidence (including `full_text` and content provenance), audited claims,
structured results, datasets and limitations enter a source-linked index. Bounded
packets split oversized units with fragment IDs; no first-N evidence/claim cutoffs
or per-schema string clipping is used. Every input fragment must be accounted for.
The fetcher's existing 4,000-character webpage retention limit is unchanged.
The plan records assignments, unused reasons and chapters that read each material.
Related sources are read in full as stored; oversized chapter inputs become
source-linked notes with original IDs. Notes guide writing; assertion verification
returns to saved original source text rather than treating notes as proof.

Outline validation checks confirmed products, user questions, available sources
and components, authors, dependencies/cycles and word allocations. A separate
model check assesses actual goals, overlap, scope and argument quality. Invalid
planning receives one corrective retry with concrete errors; a second failure
saves research and planning attempts and stops with `write_planning_failed`.
There is no fixed-outline fallback.

Writers share source-linked factual notes, names, conditions, uncertainties and
research constraints. Topological groups run sequentially; independent chapters
within a group run concurrently. Dependencies receive actual completed paragraphs
and argument summaries, not only the outline. Long chapters continue with their
completed content and outstanding goals. If planned, summary/recommendations are
written after the body, even when displayed first. One full editorial integration
pass handles transitions, terminology, duplication and certainty, then final
chapters are refreshed from the edited body. Every retry, rewrite and annotation
refinement retains the same research/evidence constraints.

Only existing typed prose, structured cards, tables, charts and sentiment
components can be attached. Chart values are built by program code from research
data; model-generated HTML and executable code are not supported. Chapter IDs,
authors and components are read from plan metadata. Legacy reports without
`writing_plan` keep their historical rendering and can still be refined.

### Verification

`verify.py` gates the document rather than the pre-writing analysis.
Deterministic checks repair formatting, resolve citation IDs and report empty or
truncated text, duplicated paragraphs and invalid percentages. There is no
minimum paragraph requirement. A real citation ID alone does not prove support.

The entire takeaway, every paragraph, highlight and component caption is read in
bounded batches. `writing_assertions` independently extracts substantive facts,
inferences and recommendations from the actual text, with exact quotations;
author-declared assertions do not substitute for this pass. `writing_support`
checks each extracted assertion against original saved evidence and verified
premises, including dates, billing conditions, products, numbers, source ownership
and independence. Official published facts may use one applicable original
official source; comparisons and empirical inferences require independent support.
Logical inferences and conditional recommendations may connect verified facts,
but must expose their premises and applicability. Audited unknowns can only be
reported as gaps; they cannot justify ranks, scores or recommendations.

Complete-text notes and the independently extracted ledger supply whole-report
consistency review: cross-chapter disagreement, missing core answers, repetition,
strengthened certainty, and final chapters inconsistent with the actual body.
The old approximately 700-character section previews are not used for new reports
or refinement. Malformed/incomplete review output or model failure stops delivery
with `verify_unavailable`; it cannot downgrade to rule-only approval.

Repair never triggers collection. The existing per-mode rounds (1/1/2) and body
rewrite budgets (2/4/6) remain. Repairs follow the dependency graph and retain the
same source context and issue directives. Mechanically worse candidates are not
accepted. Dependent summary/advice chapters are refreshed at most once per repair
round from revised body results. All changed text is re-extracted, source-checked
and reviewed again; a rewrite never automatically closes semantic findings.
Serious unresolved factual, inference or consistency issues stop delivery with
`verify_blocked`; only minor remaining findings can ship visibly flagged. Mock
can ship simulated output and explicitly states no real evidence verification.

The existing `tasks.audit_data` snapshot and read-only audit API also retain the
writing plan, material use, stage drafts/history, assertion/source-check records,
verification and errors. Planning/writing/verification failures keep `failed` task
status and create no formal report. The workspace restores sources, outline,
drafts and issues after refresh. `writing_plan` and replacement `writing_draft`
SSE events keep live writing state current. Successful reports carry optional
plan/chapter/component/assertion metadata; older JSON remains readable.

Annotation refinement reads the selected chapter's goal, actual dependency
context and all saved sources through the same writer/reviewer. It preserves a
failed candidate instead of replacing the original on serious target issues.
Cross-chapter findings are saved and shown by the verification panel; other
chapters, including user edits, are never silently overwritten. No automatic
resume or verification bypass is added.

## Model routing

`LLM_PROVIDER=mock|qwen|openai` selects one provider for the process; restart to
switch. Mock is the default. Qwen and OpenAI share an `httpx` adapter for
`/chat/completions`. Qwen uses `max_tokens` with thinking disabled; OpenAI uses
`max_completion_tokens`. JSON mode adds a JSON instruction and `json_object`
response format. Array results use an `items` wrapper, unwrapped on parsing.
Optional schemas are prompt constraints, followed by the existing tolerant
coercion; they are not a guarantee of strict server-side schema validation.

| Tier | Config variable | Used for |
|---|---|---|
| `core` / `aux` | `OPENAI_MODEL_CORE` / `QWEN_MODEL_CORE` | Sections, cross-analysis, audit review |
| `fast` | `OPENAI_MODEL_FAST` / `QWEN_MODEL_FAST` | Intake, scope discovery, dispatch, sentiment classification |

Rate-limit buckets are per tier, and the fast tier only gets its own budget when
it is genuinely a different model. `LLM_RPM_*`, `LLM_RPD_*` and `LLM_TPM_*`
are per-process local budgets (0 disables the cap), and
`LLM_MAX_CONCURRENCY` defaults to 4. Daily caps reset at midnight fixed UTC-08:00,
not according to a provider's account quota reset. Retryable network/status
failures release their concurrency lease before bounded backoff.

All LLM methods accept optional `task_kind` and `mock_context` keyword arguments.
Research call sites pass an operation and structured source context; real HTTP
requests do not include these fields. Mock copies supplied excerpts, applies the
existing sentiment keyword rules and returns actual rule-side review scores.
Unsupported pricing/persona data remains empty. Mechanical checks and rework
budgets still run, and a simulated report can remain flagged. Search, fetching,
social collection and SQLite still execute normally. Offline tests replace only
collection inputs and use a temporary database.

Mock bypasses model quotas, records `mock:` trace model names with zero tokens,
and reports `{}` for quota usage. `/health` and `/api/llm/ping` expose
`llm_provider` and `is_mock`. Persisted reports include the same metadata and a
visible `[MOCK] Simulated report` subtitle. Existing report JSON storage needs no migration.
Gemini and its SDK were removed; old `GEMINI_*` settings are ignored.

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

`POST /api/tasks` persists the identified subject, questionnaire, mode and optional
`subscription_id`. `GET /api/tasks/{id}` restores the question, questionnaire,
answers, state and report link; unknown IDs return 404. Rival selections extend
the primary subject rather than replacing it.

`GET /api/tasks/{id}/stream` reserves an unstarted task once. `TaskRunner` owns a
background producer independently of SSE connections. Concurrent subscribers
share the same producer and in-memory event buffer. Event IDs increase for that
task; `Last-Event-ID` and the `after` query parameter resume after a cursor.
Closing a subscriber never cancels the research job. The browser caps retries at
three for the lifetime of a subscription, and closes on `done` or a business
`error` event.

Completed jobs release their live buffer; reconnects use the saved terminal
sequence and report ID. Failure and interruption are terminal and require a new
task. Startup marks previously running tasks interrupted; shutdown cancels jobs
and persists interruption. This is single-process execution, not durable job
resumption after a backend restart. Deleted reports produce 410 for their task
streams rather than silently starting over.

Fatal model configuration, authentication and quota errors propagate through
fallbacks and terminate a job. Malformed model output can still use the existing
repair path, but a report whose authored sections all fail after verification
is not saved as a successful result.


## Storage

SQLite with thread-local connections (a shared connection across `to_thread`
workers deadlocks), WAL mode and a 30-second busy timeout.

Tables: `tasks`, `reports`, `evidences`, `subscriptions`, `expert_stats`,
`traces`, `report_feedback` — with indexes on every hot filter path.
