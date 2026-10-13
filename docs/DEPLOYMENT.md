# Deployment

## Local development

### Requirements

- Python ≥ 3.13, via [uv](https://docs.astral.sh/uv/)
- Node.js 20.19+ (20.x), or 22.12+; Node 24 LTS recommended

### Backend

```bash
uv sync --locked
cp backend/.env.example backend/.env    # mock by default; select qwen/openai for real inference
uv run uvicorn app.main:app --app-dir backend --reload --port 8010
```

`--app-dir backend` puts `backend/` on `sys.path`, so `app.main:app` resolves
without installing the project as a package.

Check it:

```bash
curl http://localhost:8010/health          # status, llm_configured, llm_provider, is_mock
curl http://localhost:8010/api/llm/ping    # provider completion + local quota usage
curl http://localhost:8010/api/search?q=test&num=3
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

Vite serves on 5173 and proxies `/api` to `127.0.0.1:8010`. To point at a
different backend, set `VITE_API_BASE`.

### Optional local launchers

Some maintainer worktrees may include local Windows launchers such as
`start.bat`, `stop.bat`, or `scripts/vantage.ps1`. They are convenience tools,
not part of the supported open-source startup path unless they are committed in
a future release. A fresh clone should use the backend and frontend commands
above.

## Verification

Run deterministic checks first:

```bash
uv run pytest
cd frontend
npm run build
npm run lint
npm run test
```

LLM smoke/soak checks run locally with the default mock. Search and full pipeline
scripts still require network access. For real LLM smoke checks, select a provider
and configure its key:

```bash
uv run python scripts/smoke_search.py    # provider contract shapes
uv run python scripts/smoke_llm.py       # chat, JSON mode, tier routing
uv run python scripts/soak_llm.py 20     # burst without a 429
uv run python scripts/run_pipeline.py --query "Notion vs Obsidian" --mode quick
```

`soak_llm.py` is the one that matters most. It fires a burst of concurrent calls
and asserts zero unretried 429s. If a real provider fails on quota, configure
`LLM_RPM_CORE` to fit the account's limit, or lower `LLM_MAX_CONCURRENCY`.

`run_pipeline.py` runs the full pipeline with no frontend and checks the
invariants: enough evidence, every claim sourced, no citation pointing at a
source that doesn't exist, every section written, traces recorded.

## Configuration

Everything lives in `backend/.env`. See
[`backend/.env.example`](../backend/.env.example) for the annotated list.

### LLM providers

Choose one configuration in `backend/.env` and restart the backend:

```dotenv
LLM_PROVIDER=mock
```

Mock requires no model key, follows every research stage, and marks its reports
`[MOCK] 模拟报告`. It copies source notes instead of making model conclusions,
keeps rule-derived review findings and reports zero model tokens. Web search,
fetching and social collection continue normally. An empty collection fails
explicitly rather than producing synthetic evidence.

```dotenv
LLM_PROVIDER=qwen
QWEN_API_KEY=your_model_studio_key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_CORE=qwen-plus
QWEN_MODEL_FAST=qwen-plus
```

`DASHSCOPE_API_KEY` is accepted when `QWEN_API_KEY` is empty. For another region
or a workspace domain, set the compatible base URL supplied by the console,
including `/compatible-mode/v1`; the key must belong to that same region.
See [Model Studio endpoint documentation](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope).

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL_CORE=gpt-4.1-mini
OPENAI_MODEL_FAST=gpt-4.1-mini
```

Overrides must support non-streaming text chat and JSON mode; Qwen uses thinking
disabled. Missing keys and authentication errors do not trigger mock fallback.
Gemini has been removed. Existing `GEMINI_*` settings are ignored, so migrate
your environment explicitly before running real inference.

### Local model budgets

```dotenv
LLM_RPM_CORE=0       # requests/minute; 0 disables this cap
LLM_RPD_CORE=0       # requests/day; 0 disables this cap
LLM_TPM_CORE=0       # tokens/minute; 0 disables this cap
LLM_RPM_FAST=0
LLM_RPD_FAST=0
LLM_TPM_FAST=0
LLM_MAX_CONCURRENCY=4
LLM_TIMEOUT=180
LLM_MAX_RETRIES=3
```

These are independent per-process local budgets, not provider-reported remaining
quota. Positive limits should fit your actual provider account. When core and
fast use the same model, the core bucket covers both. Request/token caps default
to disabled; the concurrency ceiling still applies. Daily counters reset at
midnight fixed UTC-08:00. Mock skips these model budgets entirely.

### Search providers

```
SEARCH_PROVIDERS=exa,tavily,ddg
```

Tried left to right. A provider that fails on auth, quota or 5xx is benched for
five minutes and the next takes over. Removing a provider is a config change, not
a code change.

DuckDuckGo needs no key and is the reason the stack runs out of the box — but it
is scraped, aggressively rate-limited and returns snippets only. Fine for
development; add Exa or Tavily before showing it to anyone.

### Reddit

Optional. Without credentials, Reddit falls back to site-restricted web search,
which loses comment scores and reply counts. To enable the real API, register a
**script** app at https://www.reddit.com/prefs/apps and set `REDDIT_CLIENT_ID`
and `REDDIT_CLIENT_SECRET`.

Hacker News needs no credentials.

## Production notes

### Building the frontend

```bash
cd frontend && npm run build      # → frontend/dist
```

Serve `dist/` from any static host and point `VITE_API_BASE` at the backend, or
put both behind one reverse proxy with `/api` routed to the backend.

### Running the backend

```bash
uv run uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8010
```

Three things to know before deploying:

1. **Single process only.** The task runner, event buffers, trace buffer and rate limiter are in-process.
   Multiple workers would each keep their own rate-limit accounting and
   collectively blow through the quota, and traces would scatter across
   processes. Scale by running separate instances with separate API keys, not by
   adding workers.

2. **Serverless does not fit.** A deep run takes minutes and holds an open SSE
   connection, which exceeds typical function timeouts. `db.py` will fall back to
   `/tmp` on a serverless host, but that is for compatibility, not a
   recommendation.

3. **No authentication.** The API has none. Do not expose it to the open
   internet without putting something in front of it. `FRONTEND_ORIGIN` scopes
   CORS but is not access control.

### Database

SQLite at `backend/app/data/vantage.db`, or wherever `VANTAGE_DB_PATH` points.
WAL mode means three files (`.db`, `.db-wal`, `.db-shm`) — back up all three, or
checkpoint first.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `llm_configured: false` | The selected real provider's key is missing from `backend/.env` |
| Authentication errors | Key wrong/revoked, model inaccessible, or Qwen key and endpoint regions differ |
| Constant 429s | Set lower `LLM_RPM_*` caps or concurrency to fit the provider account, then re-run `soak_llm.py` |
| `DailyQuotaExhausted` | Local daily budget spent. Resets at midnight fixed UTC-08:00. |
| "No search provider is available" | No key set and `ddg` is not in `SEARCH_PROVIDERS`. |
| Sections say "could not be generated" | Model calls failed. Check `/api/llm/ping`. |
| Research ends with an error | Check the selected provider, key, quota and search access; failures do not automatically restart the task. |
| Frontend loads, all data empty | Backend unreachable. A toast reports the failed request; check the proxy target. |
| Backend port is in use | Something is already on 8010. Stop that process or choose another `--port`. |
| Frontend port is in use | Vite uses `strictPort`; stop the process on 5173 or pass a different Vite port and update the backend origin. |

## Local task recovery and security

Refreshing the workspace or briefly losing the browser connection reattaches to
the original task. Leaving the page does not stop the job. Restarting the backend
marks unfinished work interrupted; create a new task to retry. Reports that
finished before the restart remain available. Development reloads have the same
interruption behavior. Do not run multiple workers against the same database.

The API is for trusted local single-user use. It has no authentication, user
isolation or public ingress throttling. Source fetching blocks local/private
addresses, validates every redirect, pins Host/TLS SNI to validated public IPs,
and limits decoded response bodies to 2 MiB. An unresolved source hostname is
rejected. Automatic robots.txt checks are not implemented.

The watchlist's **Research now** action creates a quick task associated with that
subscription. Successful completion updates its run count and latest report.
No scheduler or background periodic monitoring is provided.

Known development dependency advisories and the latest verification scope are
recorded in [REVIEW.md](REVIEW.md). Do not use `npm audit fix --force` to migrate
Tailwind as part of routine setup.
