# Local deployment

Run one backend process on your computer. Do not expose this unauthenticated
single-user application as a public service.

```powershell
uv sync --locked
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8010
```

```powershell
cd frontend
npm ci
npm run dev
```

Vite serves port 5173 and proxies /api to 127.0.0.1:8010.
FRONTEND_ORIGIN controls CORS; VITE_API_BASE can select another local origin.

backend/.env resolves independently of the working directory.
LLM_PROVIDER selects mock, qwen or openai; all roles use *_MODEL_CORE.
Existing *_MODEL_FAST settings may remain but research does not route roles
to different models. Real failures never fall back to mock.

RESEARCH_TOKEN_LIMIT=100000 and RESEARCH_TIME_LIMIT_SECONDS=1200 include role
calls, retries, review and two reworks. Missing usage is estimated; these are
resource caps, not money guarantees. Provider rate/concurrency quotas are separate.
SCOPE_TOKEN_LIMIT=12000 and SCOPE_TIME_LIMIT_SECONDS=120 bound all preparation
rounds for one task, excluding time spent waiting for the user's answers.
SEARCH_PROVIDERS chooses optional keyed Exa/Tavily and keyless ddg fallback.

SQLite defaults to backend/app/data/vantage.db; VANTAGE_DB_PATH overrides it.
Schema v3 incrementally adds annotations to v2; reports, versions, evidence and
configuration remain intact. Pre-v2 databases retain the earlier one-time legacy
reset policy. Failed migration rolls back and stops startup. Do not downgrade a
v3 database. Environment files and keys stay outside version control.

## Recovery

- Refresh restores checkpoints and streams; it does not restart research.
- Restart marks unfinished work interrupted. Manual retry creates a new task.
- Interrupted preparation retains suggestions and answers; use its explicit
  retry or manual completion. Research still requires Confirm scope & start.
- Transport errors do not prove task failure; refresh or inspect History.
- HTTP 409 preserves current work and your candidate/draft. Inspect current
  content; stale candidates require new research from the current base.
- Missing sources, unknown dates and conflicts remain visible.
- /health checks configured readiness without making a model call.

Offline browser acceptance runs against the separate database created by
`python scripts/ui_fixture.py`. The mutation harness requires its fixture-only
health endpoint; it refuses to mutate the normal report database. Read-only
saved-report checks use `node scripts/browser_check.cjs --report REPORT_ID`.
The harness expects an available `playwright-core` via PLAYWRIGHT_MODULE_PATH
and installed Chromium. It does not install browsers or call paid models.
