# Deployment

## Local development

### Requirements

- Python ≥ 3.13, via [uv](https://docs.astral.sh/uv/)
- Node.js ≥ 20

### Backend

```bash
uv sync
cp backend/.env.example backend/.env    # then fill in GEMINI_API_KEY
uv run uvicorn app.main:app --app-dir backend --reload --port 8010
```

`--app-dir backend` puts `backend/` on `sys.path`, so `app.main:app` resolves
without installing the project as a package.

Check it:

```bash
curl http://localhost:8010/health          # {"status":"ok","llm_configured":true}
curl http://localhost:8010/api/llm/ping    # live model call + remaining quota
curl http://localhost:8010/api/search?q=test&num=3
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite serves on 5173 and proxies `/api` to `127.0.0.1:8010`. To point at a
different backend, set `VITE_API_BASE`.

## Verification

Run these in order. Each one gates the next.

```bash
uv run python scripts/smoke_search.py    # provider contract shapes
uv run python scripts/smoke_llm.py       # chat, JSON mode, tier routing
uv run python scripts/soak_llm.py 20     # burst without a 429
uv run python scripts/run_pipeline.py --query "Notion vs Obsidian" --mode quick
```

`soak_llm.py` is the one that matters most. It fires a burst of concurrent calls
and asserts zero unretried 429s. If it fails, your `GEMINI_RPM_CORE` is higher
than your real quota — lower it, or lower `GEMINI_MAX_CONCURRENCY`.

`run_pipeline.py` runs the full pipeline with no frontend and checks the
invariants: enough evidence, every claim sourced, no citation pointing at a
source that doesn't exist, every section written, traces recorded.

## Configuration

Everything lives in `backend/.env`. See
[`backend/.env.example`](../backend/.env.example) for the annotated list.

### Gemini quotas

Free-tier limits change. Read your real numbers from
[AI Studio](https://aistudio.google.com/rate-limit) and set them explicitly:

```
GEMINI_RPM_CORE=10       # requests/minute on the core model
GEMINI_RPD_CORE=1500     # requests/day
GEMINI_TPM_CORE=250000   # tokens/minute
GEMINI_MAX_CONCURRENCY=4
```

Daily caps bound throughput more than per-minute ones: at ~1,500 requests/day and
25-35 calls per deep run, expect roughly 40-50 runs a day.

The limiter treats these as independent sliding windows. Exceeding any one of
them produces a 429, so all three matter.

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

1. **Single process only.** The trace buffer and the rate limiter are in-process.
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
| `llm_configured: false` | `GEMINI_API_KEY` missing from `backend/.env` |
| `API_KEY_INVALID` on every call | The key is wrong or revoked. Generate a fresh one in AI Studio. |
| Constant 429s | `GEMINI_RPM_CORE` exceeds your real quota. Lower it and re-run `soak_llm.py`. |
| `DailyQuotaExhausted` | Daily cap spent. Resets at midnight US/Pacific. |
| "No search provider is available" | No key set and `ddg` is not in `SEARCH_PROVIDERS`. |
| Sections say "could not be generated" | Model calls failed. Check `/api/llm/ping`. |
| Report with 1 claim and empty sections | The pipeline degraded gracefully around a failing model — collection still worked. Check the key. |
| Frontend loads, all data empty | Backend unreachable. A toast reports the failed request; check the proxy target. |
