# Vantage · AI Competitive Intelligence

> Every conclusion carries its source.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Gemini](https://img.shields.io/badge/Gemini-free%20tier-4285F4?logo=google&logoColor=white)](https://ai.google.dev/)

Vantage is a competitive-intelligence workbench that researches a market the way
an analyst team would: it assembles a group of specialists, collects real
evidence from the open web, cross-checks it, argues with itself, and writes a
report where every claim links back to the page it came from.

The point is not that it writes quickly. The point is that you can check it.

- **Real collection.** Live web search, real page fetching, Reddit and Hacker
  News through their APIs. When a search finds nothing, the report says so
  rather than filling the gap.
- **No claim without evidence.** Every conclusion carries evidence IDs.
  Fabricated citations are filtered out before they reach the page — a claim
  whose sources don't exist drops to "unverified" instead of looking sourced.
- **Visible reasoning.** Every model call — prompt, output, tokens, decision —
  is recorded and replayable, live during the run and afterward in the report.

---

## Core ideas

| | |
|---|---|
| **Multi-agent team** | 52 specialists across three tiers (decision / strategy / execution). A director picks the right team for each brief. |
| **Deep Research pipeline** | `intake → orchestrator → collect → analyze → audit → write → verify → done`, with a rework loop that actually fires |
| **Real web collection** | Multi-angle search, full-text extraction, relevance and garbled-text filtering |
| **Structured knowledge** | Feature trees, pricing models and user personas as typed objects, rendered as matrices, tables and cards |
| **Computed credibility** | 0-100 per source from type, domain authority, recency and fetch quality — not a hardcoded number |
| **Measured impact** | Time saved, source coverage, consistency and accuracy, each shipped with the formula that produced it |
| **Verified before delivery** | Every inline citation is resolved against real evidence; the finished report is read as a whole for contradictions and unsupported claims, and failing sections are rewritten |
| **Full trace** | Every agent's prompt, output, token cost and decision, queryable and replayable |
| **Annotation-driven follow-up** | Highlight a passage, add a note, and re-research just that section |
| **Three depths** | Quick / Deep / Expert, scaling search volume, section count and rework rounds |

---

## The four rules

These are enforced in code, not just documented:

1. **No claim without evidence.** A conclusion with no sources is marked
   `unverified`, never asserted. ([`models.make_claim`](backend/app/core/models.py))
   The same rule reaches the prose: a citation in the finished text that matches
   no collected source is removed before delivery.
   ([`verify.check_sections`](backend/app/core/verify.py))
2. **Cross-validation.** High confidence requires two or more *independent
   domains*. Two citations from the same site is corroboration, not
   verification.
3. **Rework closes the loop.** When quality falls short, work goes back to
   collection or analysis — the bar does not move.
   ([`audit.decide_rework`](backend/app/core/audit.py))
4. **Observability.** Every model call lands in the trace.
   ([`core/trace.py`](backend/app/core/trace.py))

---

## Stack

**Frontend** · React 19 · TypeScript · Vite · Tailwind · Zustand · React Router · ECharts · D3 · Framer Motion

**Backend** · FastAPI · SQLite · Server-Sent Events

**LLM** · Google Gemini. The free tier has no Pro model, so the pipeline runs on
Flash for quality-critical work and Flash-Lite for light tasks, paced by a
token-bucket rate limiter (see [Rate limiting](#rate-limiting)).

**Search** · Exa → Tavily → DuckDuckGo, tried in order with automatic failover.

**Social** · Reddit and Hacker News via their APIs; G2, Trustpilot, Capterra,
YouTube and X via site-restricted search.

Architecture and data flow: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Layout

```
.
├── backend/app/
│   ├── core/            # orchestration, LLM, search, fetching, credibility,
│   │                    #   audit, verify, trace
│   │   └── search/      # provider chain: exa / tavily / ddg
│   ├── data/            # experts.json — the 52-analyst roster
│   └── main.py          # FastAPI entry point
│
├── frontend/src/
│   ├── components/      # VTracePanel, VDataGrid, VChart, VAvatar, …
│   ├── pages/           # 11 pages
│   ├── store/           # Zustand state
│   ├── lib/             # api.ts, labels.ts, format.ts
│   └── hooks/           # useTaskStream (SSE)
│
├── scripts/             # vantage.ps1 launcher, smoke tests, pipeline harness
├── start.bat            # one-click start  ┐ wrappers around scripts/vantage.ps1
├── stop.bat             # one-click stop   ┘
└── docs/                # architecture, agents, deployment
```

---

## Getting started

### Requirements

- Python ≥ 3.13 (managed by [uv](https://docs.astral.sh/uv/))
- Node.js ≥ 20

### Quick start (Windows)

```
start.bat        # installs deps, starts both services, opens the browser
stop.bat         # stops both and frees their ports
```

Double-click either from Explorer, or run them from a terminal. `start.bat`
creates `backend/.env` from the example on first run — put your
`GEMINI_API_KEY` in it ([get one here](https://aistudio.google.com/apikey)) and
start again.

Both are wrappers around [`scripts/vantage.ps1`](scripts/vantage.ps1), which
takes a few more options:

```powershell
.\scripts\vantage.ps1 -Action status        # what is running, and is the key loaded
.\scripts\vantage.ps1 -Action restart
.\scripts\vantage.ps1 -Reload -Show         # uvicorn --reload, visible consoles
.\scripts\vantage.ps1 -BackendPort 9000 -FrontendPort 3000
```

Service logs go to `.run-logs/`. Reload is off by default — a file-watch restart
mid-run would kill an in-flight research pipeline and its SSE connection.

The manual steps below are the same thing, and the reference for other
platforms.

### 1. Configure

```bash
cp backend/.env.example backend/.env
```

Fill in at minimum `GEMINI_API_KEY` ([get one here](https://aistudio.google.com/apikey)).
Search works without a key via DuckDuckGo, but add `EXA_API_KEY` or
`TAVILY_API_KEY` for anything beyond local development — see [Search providers](#search-providers).

### 2. Backend

```bash
uv sync
uv run uvicorn app.main:app --app-dir backend --reload --port 8010
```

Backend at http://localhost:8010 · health check `/health` · model check `/api/llm/ping`

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend at http://localhost:5173 (proxies `/api` to port 8010).

### Verify before you rely on it

```bash
uv run python scripts/smoke_search.py    # every search provider returns the contract shape
uv run python scripts/smoke_llm.py       # chat, JSON mode, tier routing, quota
uv run python scripts/soak_llm.py        # 20 concurrent calls without a single 429
uv run python scripts/run_pipeline.py --query "Notion vs Obsidian" --mode quick
```

`run_pipeline.py` runs the whole thing headlessly and asserts the invariants the
product rests on: enough evidence, every claim sourced, no citation pointing at
a source that doesn't exist, every section written, traces recorded.

---

## Configuration

All secrets come from the environment. See [backend/.env.example](backend/.env.example)
for the full list.

| Variable | Purpose | Required |
|---|---|---|
| `GEMINI_API_KEY` | Google AI Studio key | yes |
| `GEMINI_MODEL_CORE` / `GEMINI_MODEL_FAST` | Model per tier | no (has defaults) |
| `GEMINI_RPM_*` / `GEMINI_RPD_*` / `GEMINI_TPM_*` | Free-tier quotas | no (verify yours) |
| `GEMINI_MAX_CONCURRENCY` | In-flight call ceiling | no |
| `SEARCH_PROVIDERS` | Ordered failover chain | no |
| `EXA_API_KEY` / `TAVILY_API_KEY` | Search providers | recommended |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Reddit API | no (falls back to search) |
| `FRONTEND_ORIGIN` | CORS allow-list | no |

### Rate limiting

This is the part that makes the free tier usable. Gemini allows roughly 10
requests per minute on Flash, while the pipeline fans out up to 12 concurrent
section writes. [`core/ratelimit.py`](backend/app/core/ratelimit.py) enforces
requests-per-minute, requests-per-day and tokens-per-minute as independent
sliding windows, with a concurrency semaphore and FIFO fairness so a burst of
section writes cannot starve the call that unblocks the next stage.

Set `GEMINI_RPM_CORE` too high and you will 429 constantly; too low just runs
slower. Check your real numbers at
[AI Studio](https://aistudio.google.com/rate-limit) and confirm with
`scripts/soak_llm.py`.

A deep run makes roughly 25-35 model calls. At 10 RPM that is a floor of two to
three minutes — expected for deep research, and the UI reports queue depth so it
reads as paced rather than stalled.

### Search providers

Free-tier budgets as of July 2026:

| Provider | Free allowance | Notes |
|---|---|---|
| **Exa** | $20 signup + $10/month (~1,400 searches) | Neural search, returns page text |
| **Tavily** | 1,000 credits/month | Returns cleaned content, can skip fetching |
| **DuckDuckGo** | Unlimited, no key | Scraped and rate-limited; fine for dev, not for a demo |

A provider that 401s or exhausts its quota is benched for five minutes and the
next one takes over. An empty result set is *not* a failover trigger — the
provider worked, it just found nothing.

---

## Security

- Every secret is read from the environment. Nothing is hardcoded.
- `.env` and `*.db` are gitignored.
- CORS is scoped to `FRONTEND_ORIGIN`, not `*`.
- Collection respects `robots.txt` and rate limits, and uses public sources only.

---

## Documentation

| | |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Modules, data flow, the pipeline stage by stage |
| [docs/AGENTS.md](docs/AGENTS.md) | The 52 analysts, message protocol, the four rules |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Local setup, production notes, troubleshooting |

---

## License and attribution

**[AGPL-3.0](./LICENSE).** You may use, modify and distribute this freely, but
any modified version — including one offered as a network service — must also be
released under AGPL-3.0.

Vantage is a US-market derivative of [**VerdaAI (青野 Verda)**](https://github.com/kangjiayao14/VerdaAI-Investigator), which established 
the multi-agent Deep Research architecture, the evidence-to-claim-to-confidence
model, the rework loop and the trace system. Vantage keeps that architecture and
replaces the provider integrations (Zhipu GLM → Gemini, Bocha → Exa/Tavily/DDG,
Chinese social platforms → Reddit/HN/review sites) along with all content and
market grounding. As a derivative work it inherits AGPL-3.0.
