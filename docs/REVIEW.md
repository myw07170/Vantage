# Product direction and restored UI acceptance

Validation date: October 10, 2026 (America/Los_Angeles).
Branch: `codex/product-direction-refactor`, created from local `main`.

## Implemented behavior

Vantage is a local, single-user software/SaaS comparison tool. React, FastAPI,
SQLite, model adapters, search/fetch, TaskRunner and SSE are retained. English
pages preserve the existing logo, colors and typography.

- Collector prepares a brief understanding summary, prefilled product/topic
  cards and a choice questionnaire before separate explicit research start.
  User edits and answers survive followups; websites stay provisional until
  identity confirmation. Up to four products, including your own; no inferred
  competitors. Broad scopes require acknowledgment and strategic questions require
  written boundaries. Preparation has a cumulative 12000-token / 120-second
  execution budget, excluding user answer time.
- Independent Collector, Analyst and Reviewer calls use the same configured core
  model. Writing belongs to Analyst. Up to two targeted reworks share one budget;
  resolved issues stop early.
- Atomic comparison items, a brief, dated changes, evidence and review records
  replace fixed long reports. Stable IDs, quotations, conditions and dependency
  links support local review invalidation.
- Citation validity and semantic support are separate. Reviewer assessments
  require locatable witnesses. Vendor claims and external experiences have
  separate source attribution. Domain/citation counts do not establish support.
- Pricing retains plan, currency, period, seat count, unit and applicable
  conditions. Charts require supported, finite data with identical conditions.
  No exchange-rate conversion or invented values.
- Background starts are independent of SSE subscribers. Per-task defaults are
  100,000 tokens and 1,200 seconds. Reservations precede calls; retries count;
  absent/empty usage and failed attempts use conservative estimates.
- Evidence, drafts, review and diagnostics are checkpointed. Budget exhaustion
  delivers existing new work with explicit limitations, or fails when no new
  usable work was produced. Restart interrupts tasks without model calls;
  retry creates a new task.
- Follow-ups search and fetch fresh material. Follow-ups/reviews persist separate
  candidates. Explicit save/apply/restore checks the base version transactionally
  and returns HTTP 409 on conflict. Restore creates a new immutable version.
- Expert resources, knowledge base, relationship graph, monitoring, legacy
  refinement/feedback and unused D3/ECharts dependencies are removed.
- Schema v3 adds annotations incrementally to v2. Existing app configuration,
  reports, evidence and versions are retained. Initialization failure rolls back
  and stops startup. Only pre-v2 databases use the earlier one-time legacy reset.
- Original centered homepage composition, report body beside Sources & notes,
  table/brief/changes navigation, citation-to-source jumps and a full-screen
  three-column research workspace are restored. Narrow screens use a source
  drawer and workspace tabs. Activity summaries come from real operations;
  traces, tokens and elapsed time are expandable.
- Four-color highlights and multi-item notes persist in SQLite. UTF-16 offsets,
  exact quotes and context preserve emoji/repeated-text anchors. Annotation CAS
  conflicts retain drafts. Save/apply/restore inherit notes atomically; ambiguous
  changed passages retain unanchored notes. Notes never alter review states.

## Offline acceptance

| Check | Result |
| --- | --- |
| Backend `python -m pytest -q -p no:cacheprovider` | 160 passed |
| Frontend `npm run test -- --run` | 17 passed |
| Frontend `npm run build` | Passed |
| Frontend `npm run lint` | Passed |
| Local headless Chromium acceptance | 22 offline scenarios passed; no page JavaScript exceptions |
| Narrow screens | Homepage, report/source drawer, scope confirmation and workspace tabs checked at 390 px |
| Database | Actual v2 DB upgraded to v3; all existing table rows and backend/.env hashes unchanged |
| Saved live report | Read-only browser check passed against the normal Qwen-configured service; no additional research task created |

Tests use isolated SQLite databases, deterministic sources and simulated roles.
They cover ambiguous products, namesakes, impostor domains/community pages,
billing conditions, missing release dates, locatable but unsupported compound
claims, source conflict, ungrounded reviewer opinions, cross-product inferences,
dependency invalidation, invalid chart values, rework limits/early completion,
budgets, partial delivery, empty-result failure, restart/retry, candidates,
transaction races, restore, multiple subscribers, replay cursors, and one-time
cleanup rollback.

Additional tests cover AI prefill, combined product names, namesake choices,
unrequested-product filtering, missing-information questions, failed website
verification, retained user edits, running-request deduplication, cumulative
preparation budget, answer waiting time, preparation interruption, UTF-16 emoji
boundaries, repeated text, cross-item notes, annotation revision conflicts,
candidate/base note inheritance, changed-context invalidation, terminal role
states, and rollback of a failed incremental migration.

Browser scenarios include source expansion/jump, four visibly distinct highlight
colors, cross-item notes, emoji/repeated-text offsets, note edit/delete, refresh
persistence, note conflict draft retention after refresh, note-triggered fresh
research, candidate preview/apply/history, restore, content edit conflicts,
keyboard-operated examples/highlight controls, reduced-motion mode, AI scope
prefill/explicit confirmation, mobile drawer/tabs and finished workspace refresh.
Mutation runs require the fixture-only health endpoint and use a separate marked
database. Screenshots are under `.run-logs/ui/`.

The main homepage source/styles were rendered in an isolated local reference
and compared with the restored composer (same font/palette/width, glow, textarea,
send control and four cards). The reference omits the sidebar and disables its
API actions. Report/workspace structure was checked against main's source and
current desktop/narrow-screen screenshots; no full legacy report fixture was
run. This is visual/interaction acceptance, not a pixel-diff certification.

The actual migration preserved 2 task rows, 1 report, 1 immutable version,
60 evidence rows and 58 diagnostic rows, checked by hashes before and after
startup. `.run-logs/v3-preservation.json` records the result. This UI restoration
used offline fixtures and the existing real report only; it did not run another
paid preparation or research task.

## One live Notion / Obsidian run

The existing Qwen configuration was used once with the three default topics,
current state plus 90-day changes, and default budgets. Search retained the
existing DuckDuckGo fallback; no paid service was added.

| Measurement | Recorded result |
| --- | --- |
| Task | `t_13d0c53a51f940c1` |
| Report | `r_3a2a17d342b24842` |
| Version | `v_20f2afe4016e42ab` |
| Provider / configured model | Qwen / `qwen3.8-max` |
| Elapsed time | 394.32 seconds (about 6 minutes 34 seconds) |
| Tokens | 81,831; provider-reported, not estimated |
| Stored evidence records | 60 (including fresh rework captures, not 60 independent sources) |
| Report items | 25 |
| Recorded review status | 11 Supported; 13 Unknown; 0 Conflicting; 1 Pending review |
| Delivery | Partial, persisted successfully |
| Stop reason | Insufficient remaining tokens to reserve the next model call |
| Local configuration | SHA-256 comparison confirmed `backend/.env` unchanged |

The first rework gathered fresh sources, then the next Analyst call's reservation
would have exceeded the task limit. Automatic work stopped and preserved the
existing reviewed result and new sources. A successful task means an artifact
was saved, not that every statement was established.

Unresolved items include a compound security assertion whose quotation did not
establish SAML, incomplete billing conditions, an unlocatable quotation, a
judgment without factual dependencies, and changes lacking verified effective
dates. No unconditional recommendation or chart was generated from those items.

This run also exposed overly strict cross-product citation handling in briefs
and a conflation of billing/date completeness with citation validity. Both were
corrected and covered by offline regression tests. The original live snapshot is
retained unchanged; it is not silently relabeled or represented as a second live
validation of those fixes.

Artifacts (local, ignored by Git):

- `.run-logs/live-comparison.json`: immutable exported version and source context.
- `.run-logs/live-comparison.summary.json`: counts, timing, tokens and limitations.
- SQLite history: the same report/version can be opened after normal service startup.

## Practical boundaries

The product is a localhost, trusted single-user application with one backend
process. Restart preserves artifacts but does not resume in-flight work.
Source availability, publication metadata and model interpretation remain
variable. Supported means support from the listed evidence under the stated
conditions, not independent certification of a vendor claim. The measured run
met the 5-8 minute target once; that is neither a fixed latency commitment nor a
requirement for every future run.
