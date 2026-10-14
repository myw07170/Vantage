<img src="frontend/public/brand/vantage-logo.png" alt="Vantage" width="112" />

# Vantage · AI Competitive Intelligence

> Every conclusion carries its source.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LLM](https://img.shields.io/badge/LLM-mock%20%7C%20qwen%20%7C%20openai-4285F4)](#configuration)

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
| `uv run pytest` | 101 passed: staffing, provider contracts, API, task lifecycle, collection security and offline pipelines |
| `npm run test` in `frontend/` | 11 passed: failed requests, SSE retries/deduplication/termination and report caches |
| `npm run build` in `frontend/` | Passes |
| `npm run lint` in `frontend/` | Passes |
| LLM smoke tests | Mock runs without a key or model network; Qwen/OpenAI need their own keys |
| Search smoke tests | DuckDuckGo can run keyless; Exa/Tavily require keys |
| Live collection + mock quick pipeline | Both Notion and Obsidian collected; 69 evidence records, 7 sections, 46 trace spans |

Important caveats:

- The FastAPI backend has **no authentication**. Do not expose it directly to
  the public internet without an auth layer or reverse proxy in front of it.
- Long research runs hold an SSE connection open for minutes, so typical
  short-timeout serverless deployments are a poor fit.
- Configure a real LLM provider for analytical conclusions. The default mock
  produces explicitly marked source notes for development; search and collection
  still need network access. Account quotas vary by provider and project.
- Task execution continues when a browser disconnects. Refreshing restores the
  original task; restarting the backend interrupts unfinished work. Use one
  backend process and create a new task to retry a failure or interruption.
- Some Windows convenience launchers used by the maintainer may exist locally
  (`start.bat`, `stop.bat`, `scripts/vantage.ps1`), but they are not part of
  the supported open-source startup path unless committed in a future release.

## Stack

**Frontend:** React 19, TypeScript, Vite, Tailwind CSS, Zustand, React Router,
ECharts, D3, Framer Motion.

**Backend:** FastAPI, SQLite, Server-Sent Events, Pydantic settings, `httpx`,
Beautiful Soup, Trafilatura.

**LLM:** `mock`, Qwen (Model Studio / DashScope), or OpenAI. Real completions
use OpenAI-compatible HTTP through `httpx`; no model SDK is required. Provider,
model names, local quotas, timeouts and concurrency are environment settings.

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
- Node.js 20.19+ (20.x), or 22.12+; Node 24 LTS recommended
- npm
- A Qwen or OpenAI API key for real model inference; mock needs no model key

### 1. Install Python dependencies

From the repository root:

```bash
uv sync --locked
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

For development, the default is:

```text
LLM_PROVIDER=mock
```

For real research, select `qwen` or `openai` and configure its key (examples below).
Restart the backend after changing providers. Search can fall back to
DuckDuckGo without a provider key, but serious runs are
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
npm ci
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
| `LLM_PROVIDER` | `mock` (default), `qwen`, or `openai`; restart to switch | no |
| `OPENAI_API_KEY` | OpenAI model key | for `openai` |
| `QWEN_API_KEY` / `DASHSCOPE_API_KEY` | Model Studio key; QWEN_API_KEY takes precedence | for `qwen` |
| `OPENAI_BASE_URL` / `QWEN_BASE_URL` | Compatible API base URLs | no |
| `OPENAI_MODEL_CORE/FAST` / `QWEN_MODEL_CORE/FAST` | Core/fast models; defaults gpt-4.1-mini / qwen-plus | no |
| `LLM_RPM_*` / `LLM_RPD_*` / `LLM_TPM_*` | Local quota caps; default 0 disables the cap | no |
| `LLM_MAX_CONCURRENCY` | Maximum concurrent real model calls; default 4 | no |
| `LLM_TIMEOUT` / `LLM_MAX_RETRIES` | Request timeout (180 seconds) / retries (3) | no |
| `SEARCH_PROVIDERS` | Ordered provider chain, for example `exa,tavily,ddg` | no |
| `EXA_API_KEY` / `TAVILY_API_KEY` | Optional paid/free-tier search providers | recommended |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Optional Reddit API credentials | no |
| `FRONTEND_ORIGIN` | Comma-separated CORS allow-list | no |

### Provider Examples

```dotenv
# Development: no model credentials. Search and collection still use network.
LLM_PROVIDER=mock
```

```dotenv
# Alibaba Cloud Model Studio / DashScope (Beijing default)
LLM_PROVIDER=qwen
QWEN_API_KEY=your_model_studio_key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_CORE=qwen-plus
QWEN_MODEL_FAST=qwen-plus
```

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL_CORE=gpt-4.1-mini
OPENAI_MODEL_FAST=gpt-4.1-mini
```

For Qwen, use a key and base URL from the same region. Override `QWEN_BASE_URL`
with your console's regional/workspace endpoint, including `/compatible-mode/v1`;
see [Model Studio endpoint documentation](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope).
Model overrides must support non-streaming text chat and JSON mode (Qwen runs
with thinking disabled). There is no automatic fallback to mock on real failures.
Gemini has been removed and old `GEMINI_*` settings no longer have any effect.

Mock follows all research stages and uses supplied source excerpts, keyword
sentiment and rule-based reviews. It does not infer product pricing, market shares
or customer personas. Reports carry `llm_provider`, `is_mock`, and a visible
`[MOCK] 模拟报告` subtitle that survives reloads and title edits. Mock traces
identify the simulated model and report zero model tokens. An empty evidence
collection still fails explicitly. Mock is an LLM substitute, not a fully offline
collection mode; offline tests supply collection fixtures instead.

`/health` and `/api/llm/ping` include `llm_provider` and `is_mock` alongside their
existing fields. Mock ping returns `ready` and an empty quota snapshot.

### Rate Limiting

The research pipeline can fan out many model calls while writing report
sections. `backend/app/core/ratelimit.py` enforces request-per-minute,
request-per-day, token-per-minute, and concurrency limits before calls are sent
to the selected real provider. Mock skips model quotas entirely. When core and
fast use the same model they share the core bucket.

If you see repeated `429` errors, lower the configured quotas or concurrency to
match the limits of your own provider account. These are per-process local
budgets, not remaining account quota. A cap of 0 disables it. Daily budgets reset
at midnight fixed UTC-08:00. Low caps slow runs down; the concurrency limit still
applies when request/token caps are disabled.

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
npm run test
```

Optional smoke tests that call external services:

```bash
uv run python scripts/smoke_search.py
uv run python scripts/smoke_llm.py
uv run python scripts/soak_llm.py
uv run python scripts/run_pipeline.py --query "Notion vs Obsidian" --mode quick
```

The LLM smoke and soak scripts run without keys or model network in mock mode.
Real model checks need provider access and quota. Search and full-pipeline scripts
still use network. `run_pipeline.py` executes the full pipeline headlessly and checks that
the generated report preserves the core evidence invariants.

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System modules, data flow, pipeline stages, storage, SSE behavior |
| [docs/AGENTS.md](docs/AGENTS.md) | The 52-analyst roster model, staffing protocol, grounding rules |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Local setup, production notes, and troubleshooting |
| [docs/REVIEW.md](docs/REVIEW.md) | 修复验收、删除清单、已知风险与未验证项目 |

## Security Notes

- Do not commit `backend/.env`, database files, logs, or API keys.
- `.gitignore` excludes `.env`, SQLite runtime files, `.run-logs/`,
  `node_modules/`, frontend build output, and local launcher scripts.
- CORS is scoped by `FRONTEND_ORIGIN`, but CORS is not authentication.
- The backend has no built-in users, sessions, permissions, or API tokens.
- Source fetching blocks private/reserved IPs, validates redirects and limits
  decoded bodies to 2 MiB. Automatic robots.txt compliance is not implemented;
  follow source/provider terms and crawl policies when running research.
- The production npm audit reports no advisories; seven high-severity development
  dependency entries remain. See [the review](docs/REVIEW.md) for scope and details.

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
| `llm_configured: false` from `/health` | The selected provider's API key is missing from `backend/.env` |
| `/api/llm/ping` returns an API-key error | The key is invalid, revoked, unavailable to the model, or belongs to another Qwen region |
| Repeated `429` responses | Set lower `LLM_RPM_*` caps or concurrency to fit your provider account |
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
