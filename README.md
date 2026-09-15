<img src="frontend/public/brand/vantage-logo.png" alt="Vantage" width="112" />

# Vantage · AI Competitive Intelligence

> Every conclusion carries its source.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Gemini](https://img.shields.io/badge/Gemini-configurable-4285F4?logo=google&logoColor=white)](https://ai.google.dev/)

Vantage is an evidence-traceable competitive-intelligence workbench. It takes a
market or competitor brief, staffs a multi-agent analyst team, collects live web
evidence, cross-checks claims, and writes a report whose conclusions can be
traced back to the sources that produced them.

The goal is not just fast report generation. The goal is to make the output
auditable.

## Features

- **Evidence-first research.** Vantage searches the open web, fetches pages,
  extracts usable text, scores source credibility, and keeps evidence records
  attached to the claims they support.
- **No claim without evidence.** Unsupported conclusions are marked
  `unverified`; citations that do not resolve to collected evidence are removed
  before delivery.
- **Multi-agent staffing.** A 52-specialist roster is selected per brief across
  decision, strategy, and execution layers.
- **Deep research pipeline.** The run moves through
  `intake -> orchestrator -> collect -> analyze -> audit -> write -> verify -> done`,
  with rework loops when quality gates fail.
- **Structured intelligence.** Feature trees, pricing models, personas,
  sentiment, charts, source libraries, and trace views are rendered in the UI.
- **Visible reasoning and cost.** Model calls, prompts, outputs, token usage,
  agent assignments, and decisions are recorded as trace spans.
- **Annotation-driven follow-up.** Highlight a passage, add a note, and ask the
  system to re-research that section.

## Project Status

This repository is suitable for local development and experimentation. It is not
yet a turnkey hosted service.

Current local verification:

| Check | Status |
|---|---|
| `uv run pytest` | Passes: 23 tests |
| `npm run build` in `frontend/` | Passes |
| `npm run lint` in `frontend/` | Passes |
| LLM smoke tests | Require `GEMINI_API_KEY` and network access |
| Search smoke tests | DuckDuckGo can run keyless; Exa/Tavily require keys |

Important caveats:

- The FastAPI backend has **no authentication**. Do not expose it directly to
  the public internet without an auth layer or reverse proxy in front of it.
- Long research runs hold an SSE connection open for minutes, so typical
  short-timeout serverless deployments are a poor fit.
- Gemini model names and free-tier quotas change over time. Treat
  `backend/.env.example` as a starting point and verify the current values in
  your own AI Studio project.
- Some Windows convenience launchers used by the maintainer may exist locally
  (`start.bat`, `stop.bat`, `scripts/vantage.ps1`), but they are not part of
  the supported open-source startup path unless committed in a future release.

## Stack

**Frontend:** React 19, TypeScript, Vite, Tailwind CSS, Zustand, React Router,
ECharts, D3, Framer Motion.

**Backend:** FastAPI, SQLite, Server-Sent Events, Pydantic settings, `httpx`,
Beautiful Soup, Trafilatura.

**LLM:** Google Gemini through `google-genai`. Model names, quotas, timeouts,
and concurrency are configured through environment variables.

**Search:** Exa, Tavily, and DuckDuckGo through an ordered failover chain.

**Social listening:** Reddit and Hacker News have API collectors; other public
platforms use site-restricted web search where available.

Architecture and data flow are documented in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repository Layout

```text
.
├── backend/
│   ├── .env.example          # copy to backend/.env for local secrets
│   └── app/
│       ├── core/             # orchestration, LLM, search, fetch, audit, verify
│       ├── data/             # experts.json and local SQLite runtime data
│       └── main.py           # FastAPI entry point
├── frontend/
│   ├── public/               # brand assets, avatars, offline expert roster
│   └── src/                  # React app, pages, components, stores, API client
├── docs/                     # architecture, agent model, deployment notes
├── scripts/                  # smoke tests and headless pipeline harness
├── tests/                    # deterministic backend tests
├── pyproject.toml            # Python dependencies and pytest config
├── uv.lock                   # Python lockfile
└── LICENSE                   # AGPL-3.0
```

## Getting Started

### Requirements

- Python 3.13 or newer
- [uv](https://docs.astral.sh/uv/)
- Node.js 20 or newer
- npm
- A Gemini API key for full research runs

### 1. Install Python dependencies

From the repository root:

```bash
uv sync
```

### 2. Configure the backend

Copy the example environment file and add your keys:

```bash
cp backend/.env.example backend/.env
```

On Windows PowerShell:

```powershell
Copy-Item backend/.env.example backend/.env
```

At minimum, set:

```text
GEMINI_API_KEY=your_key_here
```

Search can fall back to DuckDuckGo without a provider key, but serious runs are
more reliable with `EXA_API_KEY` or `TAVILY_API_KEY`.

### 3. Start the backend

```bash
uv run uvicorn app.main:app --app-dir backend --reload --port 8010
```

Useful backend checks:

```bash
curl http://localhost:8010/health
curl http://localhost:8010/api/llm/ping
curl "http://localhost:8010/api/search?q=test&num=3"
```

The backend reads `backend/.env` regardless of the shell working directory.

### 4. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api` to the backend
on port `8010`.

If the backend is on another origin, set `VITE_API_BASE` before starting or
building the frontend.

## Configuration

All secrets and deployment-specific settings are read from environment
variables. See [backend/.env.example](backend/.env.example) for the annotated
list.

| Variable | Purpose | Required |
|---|---|---|
| `GEMINI_API_KEY` | Google AI Studio key used for LLM calls | yes |
| `GEMINI_MODEL_CORE` / `GEMINI_MODEL_FAST` | Model names for quality-critical and light tasks | no |
| `GEMINI_RPM_*` / `GEMINI_RPD_*` / `GEMINI_TPM_*` | Rate-limit buckets for the configured models | no |
| `GEMINI_MAX_CONCURRENCY` | Maximum concurrent model calls | no |
| `SEARCH_PROVIDERS` | Ordered provider chain, for example `exa,tavily,ddg` | no |
| `EXA_API_KEY` / `TAVILY_API_KEY` | Optional paid/free-tier search providers | recommended |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Optional Reddit API credentials | no |
| `FRONTEND_ORIGIN` | Comma-separated CORS allow-list | no |

### Rate Limiting

The research pipeline can fan out many model calls while writing report
sections. `backend/app/core/ratelimit.py` enforces request-per-minute,
request-per-day, token-per-minute, and concurrency limits before calls are sent
to Gemini.

If you see repeated `429` errors, lower the configured quotas or concurrency to
match the limits of your own Google AI Studio project. If you set the values too
low, runs will be slower but should remain stable.

### Search Providers

`SEARCH_PROVIDERS` is tried left to right. A provider that fails because of
auth, quota, or server errors is temporarily benched and the next provider is
used. An empty result set is not treated as a provider failure.

DuckDuckGo needs no key and is useful for local development, but it is scraped
and rate-limited. Exa or Tavily are recommended for demos and heavier use.

## Verification

Run deterministic checks first:

```bash
uv run pytest
```

Then validate the frontend:

```bash
cd frontend
npm run build
npm run lint
```

Optional smoke tests that call external services:

```bash
uv run python scripts/smoke_search.py
uv run python scripts/smoke_llm.py
uv run python scripts/soak_llm.py
uv run python scripts/run_pipeline.py --query "Notion vs Obsidian" --mode quick
```

These smoke tests require the relevant API keys, network access, and available
quota. `run_pipeline.py` executes the full pipeline headlessly and checks that
the generated report preserves the core evidence invariants.

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System modules, data flow, pipeline stages, storage, SSE behavior |
| [docs/AGENTS.md](docs/AGENTS.md) | The 52-analyst roster model, staffing protocol, grounding rules |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Local setup, production notes, and troubleshooting |

## Security Notes

- Do not commit `backend/.env`, database files, logs, or API keys.
- `.gitignore` excludes `.env`, SQLite runtime files, `.run-logs/`,
  `node_modules/`, frontend build output, and local launcher scripts.
- CORS is scoped by `FRONTEND_ORIGIN`, but CORS is not authentication.
- The backend has no built-in users, sessions, permissions, or API tokens.
- Collection is designed for public web sources and should be used with respect
  for provider terms, robots rules, and rate limits.

## Contributing

This repository does not yet include a full contribution guide. For now:

1. Keep backend behavior covered by deterministic tests where possible.
2. Run `uv run pytest` before opening a change.
3. Run `npm run build` and `npm run lint` in `frontend/` for UI changes.
4. Keep secrets out of commits and add new environment variables to
   `backend/.env.example`.
5. Update the README or docs when a command, port, dependency, or public
   behavior changes.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `llm_configured: false` from `/health` | `GEMINI_API_KEY` is missing from `backend/.env` |
| `/api/llm/ping` returns an API-key error | The Gemini key is invalid, revoked, or unavailable to the configured model |
| Repeated `429` responses | Gemini quota or concurrency settings are higher than your project allows |
| Search returns no provider results | Provider keys are missing, exhausted, or `ddg` was removed from `SEARCH_PROVIDERS` |
| Frontend loads but data is empty | Backend is not running, the Vite proxy is wrong, or `VITE_API_BASE` points elsewhere |
| Event stream disconnects mid-run | The browser lost the SSE connection; check backend logs and reports history |
| A deep run takes minutes | Expected for multi-step research with live fetches, model calls, and rate limiting |

## License and Attribution

Vantage is released under [AGPL-3.0](./LICENSE). You may use, modify, and
distribute it freely, but modified versions offered over a network must also
make their corresponding source available under the AGPL.

Vantage's early design referenced the multi-agent Deep Research framework of
[VerdaAI (青野 Verda)](https://github.com/kangjiayao14/VerdaAI-Investigator) by
[@kangjiayao14](https://github.com/kangjiayao14). The pipeline, provider
adapters, analyst roster, verification flow, and interface have since been
substantially rebuilt for this project.
