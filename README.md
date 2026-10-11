<img src="frontend/public/brand/vantage-logo.png" alt="Vantage" width="96" />

# Vantage - Product Comparisons

A local, single-user software/SaaS comparison workspace. Confirm up to four
products and editable topics, then get an evidence-linked comparison table,
short brief and verifiable changes from the last 90 days.

Three fixed roles share one locally configured core model through independent
calls: **Collector -> Analyst -> Reviewer**, with at most two targeted reworks.
Each fact and key judgment shows **Supported**, **Unknown**, **Conflicting**, or
**Pending review**. Completion does not mean every question is resolved.

## Local setup

Python 3.13+, uv, and Node.js 20.19+ or 22.12+ are required.

```powershell
uv sync --locked
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8010
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open [the local workspace](http://localhost:5173). Run one backend process, bound
to localhost. There is no authentication or hosted-service framework.

Select LLM_PROVIDER=mock, qwen or openai in backend/.env. All three roles use the
selected provider's *_MODEL_CORE. Existing credentials/model settings are kept.
Mock produces marked source notes and Unknown semantic support; collection still
uses network unless replaced by offline fixtures.

Search follows SEARCH_PROVIDERS (Exa/Tavily/DuckDuckGo). Exa and Tavily require
optional keys; DuckDuckGo is a keyless, rate-limited fallback. Fetching blocks
private/reserved addresses, validates redirects and caps bodies at 2 MiB.

## Workflow

1. Describe the comparison. Collector suggests products, vendor websites, topics
   and relevant questions. Answer the questionnaire, update suggestions, then
   confirm identities and scope. Advanced fields remain editable. Your own
   product counts toward the four-product limit; no rivals are added for you.
2. Explicitly start. Research continues when the page disconnects.
3. Follow the three-column pipeline, activity journal and live evidence stream.
   Read the report beside Sources & notes; citation numbers locate exact sources.
   On narrow screens, sources open in a drawer.
4. Follow up on a table item or selected passage. New research creates a
   **candidate**, without changing the current report.
5. Preview and explicitly apply. Saving, applying and restoring check the base
   version; HTTP 409 never silently overwrites newer work.
6. Explicitly save manual edits. Only changed items and dependent judgments become
   Pending review. Restore an old version by creating a new version.
7. Select report or table text to highlight Important (yellow), Agree (green),
   Questionable (red) or Follow up (blue), and add a note. Notes persist in SQLite
   and can launch candidate research. Highlights never change review states.

Research tiers, expert center, knowledge base, relationship graph and monitoring
subscriptions have been removed.

## Budgets and data

RESEARCH_TOKEN_LIMIT defaults to 100000; RESEARCH_TIME_LIMIT_SECONDS to 1200.
Retries, review and up to two reworks share the task budget. Failed attempts and
missing provider usage are charged conservatively and marked estimated.
Provider RPM/TPM limits remain separate. Tokens are not a fixed-dollar promise.

Scope preparation has a separate cumulative budget: SCOPE_TOKEN_LIMIT=12000 and
SCOPE_TIME_LIMIT_SECONDS=120. Waiting for answers does not count as execution
time. Refreshing never starts preparation; failed preparation retains available
suggestions and offers explicit retry or manual completion.

SQLite saves versions, candidates, evidence, checkpoints and diagnostic summaries.
Restart interrupts unfinished work; manual retry creates a new task.
SSE subscriptions only read events and never execute research.

**Schema v3 upgrades existing v2 databases incrementally, preserving reports,
versions, evidence and configuration.** Only pre-v2 legacy databases undergo the
previously specified one-time reset. Migration failure rolls back and stops
startup. Environment and model configuration files are never modified.

Annotations use UTF-16 offsets and surrounding context. Each report version has
its own notes; current-version and note-revision checks reject stale writes with
409. Save/apply/restore inherit notes transactionally. A changed passage is
re-anchored only on a unique text/context match; otherwise its note is retained
with an explicit changed-passage label. Annotation edits do not create content
versions. Browser storage holds only unsaved drafts.

## Verification

```powershell
uv run pytest -p no:cacheprovider
cd frontend
npm run test
npm run build
npm run lint
```

Run the confirmed Notion/Obsidian case with your current configuration:

```powershell
uv run python scripts/run_pipeline.py --allow-live --out .run-logs/live-comparison.json
```

Real inference requires --allow-live. For other products, pass --scope with a JSON
ResearchScope. Results and a separate summary record review states, gaps, time and
tokens. External failures are reported without fabricated conclusions. A usual
5-8 minute wait is a measurement target, not a guarantee.

See [architecture](docs/ARCHITECTURE.md), [roles](docs/AGENTS.md),
[deployment](docs/DEPLOYMENT.md) and
[verification](docs/REVIEW.md). Licensed under [AGPL-3.0](LICENSE).
