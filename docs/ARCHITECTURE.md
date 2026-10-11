# Vantage architecture (schema v3)

React 19, TypeScript, Vite, Tailwind and Zustand connect to one FastAPI process.
SQLite uses WAL, thread-local connections and serialized writes. The original
Vantage palette, fonts, centered composer, report/source columns and full-screen
research workspace frame the newer evidence and version contracts.

## Explicit scope preparation

POST /api/tasks creates a draft without model calls. POST /tasks/{id}/prepare
returns 202 and schedules Collector using the configured core model. Payload
contains preparation status, revision, understanding summary, proposed products
and topics, questions, retained answers, errors and cumulative usage.

Preparing, awaiting_confirmation and running are separate task states.
Preparation consumes at most 12000 tokens and 120 seconds of execution by default;
waiting for answers is excluded. Repeated identical revision/request submissions
share execution, stale revisions return 409, and GET/polling/refresh never start
work. Partial proposals survive failed website checks. Restart interrupts
preparation without invoking models. Retry and manual completion are explicit.

Products are limited to names in user input/answers/edits. Combined names are
split by Collector; namesakes receive identity options. Proposed vendor URLs use
the existing search/fetch stack. A name/site match is visibly provisional until
the user confirms ownership. User edits and answers survive necessary followups.
Advanced identity fields collapse; unanswered questions must be processed before
confirmation. Scope warnings require acknowledgment, never silent trimming.

POST /tasks/{id}/start validates a ResearchScope and reserves one research job.
Scope contains 1-4 confirmed software products, websites, categories, an optional
own-product flag, editable topics/focus and current state plus 90-day changes.
Broad scopes require acknowledgment; strategic topics also require boundaries.

## Research and evidence

Collector proposes bounded queries, fetches public sources and checks external
product identity using locatable text. Vendor attribution derives from the
confirmed vendor relationship; third-party experiences remain distinct from
vendor commitments. Excerpts, context, publication/capture dates and fetching
limitations are separate fields.

Analyst writes atomic comparisons, conditional judgments, a brief and changes.
Reviewer checks citation validity mechanically and semantic support independently.
All three use the same configured core model with separate responsibility prompts.
Stable IDs connect items to quotations, conditions and dependencies. Invalid
citations are Unknown; absent semantic assessments remain Pending review.
Unresolved or cyclic dependencies cannot support a conclusion. Charts use only
supported numbers with identical measurement/billing conditions and point-level
citations. There are no inferred overall credibility scores.

At most two reworks address actionable issues and dependent conclusions;
unaffected content is preserved. Exhaustion saves available artifacts with
explicit limitations. Empty new work fails rather than claiming success.

## Background execution and visualization

Research/followup/review tasks run independently of SSE. Defaults are 100000
tokens and 1200 seconds, including retries and automatic rework. Each real attempt
reserves conservative input plus its output ceiling before calling the provider.
Usage reconciles reservations; missing usage and failed attempts keep estimates.
Quota waits, backoff, fetching and model requests respect the remaining deadline.
A ContextVar shares the budget with workers. Cancellation prevents late writes.

The event loop owns persistence. Evidence and draft/review checkpoints persist
during execution. A visualization checkpoint stores role states, overall progress,
rework round and up to 200 concise activity entries from actual searches, draft
handoffs and review issues. The left timeline, middle activity and right evidence
stream restore directly from checkpoints. Trace/usage details are collapsed.
Older saved tasks can display recorded diagnostic call summaries without inventing
a historical activity log. Narrow screens switch panels with tabs.

Events have increasing IDs; SSE supports Last-Event-ID/after cursors and client
deduplication. Transport failure is distinct from task failure. Terminal results
restore from SQLite, without requiring an entire event history. Restart interrupts
running jobs; manual research retry creates a new task and preserves artifacts.

## Versions and reader annotations

Schema v3: tasks, reports, versions, evidences, traces, annotations. The v2-to-v3
transaction only adds annotation storage and advances PRAGMA user_version.
Existing v2 data and application configuration remain intact. Only pre-v2 legacy
databases use the previous named-table reset. Migration failure rolls back and
blocks startup; unsupported future schemas also block startup.

Reports point to one current version. Immutable versions store content, kind,
candidate/applied state, base version, task and change metadata. Candidates never
move the pointer automatically. Save/apply/restore compare the current pointer
under BEGIN IMMEDIATE and return 409 on conflict. Restore creates a new snapshot.
Manual edits invalidate only changed items and transitive dependents.

Annotations store color, comment, revision, version, original quotes, content IDs,
UTF-16 start/end offsets and surrounding context. Emoji boundaries are validated.
A cross-item selection becomes one note with multiple anchors. Current-version
and annotation-revision checks guard write/update/delete; historical versions
and candidates are read-only. Notes do not create content versions or change
evidence review states. Unsaved note/content drafts remain in browser storage.

Content version transactions clone annotations atomically. Save and candidate
apply use the latest notes on the base current version; restore uses historical
notes. Unchanged text retains offsets. Changed text requires a unique exact
quote/context match; otherwise the retained note is visibly unanchored.
Citation buttons expand, scroll and highlight the right source card. Notes locate
their marked passages. The same behavior works in the narrow-screen drawer.

## Interfaces

Requests use snake_case and reject unknown fields where typed contracts apply.
Legacy mode, subscription, expert, monitoring, knowledge, feedback and synchronous
refine interfaces are removed.

- POST /api/tasks {query}; GET /api/tasks and /api/tasks/{id}.
- POST /api/tasks/{id}/prepare {base_revision,answers,draft_scope?} -> 202.
- POST /api/tasks/{id}/start ResearchScope; POST /retry creates a new task.
- GET /api/tasks/{id}/stream and /trace.
- GET /api/reports and /api/reports/{id}; PATCH title/starred; DELETE history.
- GET /api/reports/{id}/versions and /versions/{version_id}.
- POST /followups {base_version_id,target_ids,selected_text,question}.
- POST /reviews {base_version_id,target_ids?}.
- POST /edits {base_version_id,edits:{item_id:text}}.
- POST /apply {base_version_id,candidate_version_id}.
- POST /restore {base_version_id,version_id}.
- GET /annotations?version_id=...; POST /annotations
  {version_id,anchors:[{item_id,start,end,quote,prefix?,suffix?}],color,comment}.
- PATCH /annotations/{annotation_id} {version_id,revision,color?,comment?}.
- DELETE /annotations/{annotation_id}?version_id=...&revision=....
- GET /api/reports/{id}/trace; GET /api/settings exposes public defaults.

Annotation routes are relative to /api/reports/{id}. Colors are sun, ok, risk,
info (Important, Agree, Questionable, Follow up). FastAPI /docs lists full models.
