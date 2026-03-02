# mailwise

**Intelligent email triage powered by LLMs — classify, route, and draft responses automatically.**

[![Quality Gates](https://github.com/yourusername/mailwise/actions/workflows/quality.yml/badge.svg)](https://github.com/yourusername/mailwise/actions)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![TypeScript](https://img.shields.io/badge/typescript-5.x-blue)
![Tests](https://img.shields.io/badge/tests-1680%2B-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-93%25-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)

Stop manually sorting emails. mailwise connects to your Gmail, classifies incoming messages using AI, routes them to the right team via Slack and HubSpot, and generates context-aware draft replies — all through a single deployment command.

## How It Works

```mermaid
graph LR
    A[📧 Gmail] --> B[Ingest]
    B --> C[Classify]
    C --> D[Route]
    D --> E[🔔 Slack]
    D --> F[📊 HubSpot]
    C --> G[Draft Reply]
    G --> H[📧 Gmail Drafts]

    style A fill:#4285F4,stroke:#333,color:#fff
    style E fill:#4A154B,stroke:#333,color:#fff
    style F fill:#FF7A59,stroke:#333,color:#fff
    style H fill:#4285F4,stroke:#333,color:#fff
```

Each email flows through a **5-stage pipeline** — ingest, classify, route, CRM sync, and draft generation. Every stage commits independently, retries with exponential backoff, and never loses data. If Slack is down, your email is still classified. If the LLM provider has an outage, a heuristic classifier takes over.

## Key Features

**AI Classification**
- Multi-provider LLM support (OpenAI, Anthropic, Ollama) via LiteLLM — switch models via config, not code
- 5-layer prompt injection defense: input sanitization, defensive prompts, data delimiters, output validation, no tool access
- Heuristic fallback classifier when LLM is unavailable
- Few-shot learning from human feedback

**Smart Routing**
- Configurable routing rules with 6 condition operators
- Slack notifications with Block Kit formatting
- HubSpot CRM sync with idempotent 6-operation chain
- Automated context-aware draft replies with organizational tone

**Production Infrastructure**
- Celery task pipeline with independent stage commits and automatic retry
- DB-enforced email state machine (12 states, explicit transitions)
- Structured JSON logging with PII sanitization and correlation IDs
- JWT authentication with Redis-backed refresh tokens
- React dashboard with 12 pages, dark mode, and real-time analytics

```
1,680+ tests  ·  93% coverage  ·  48 API endpoints  ·  6 Docker services  ·  5 integrations
```

## Quick Start

```bash
git clone https://github.com/yourusername/mailwise.git
cd mailwise
cp .env.example .env    # Edit with your API keys
docker compose up -d    # All 6 services start with health checks
```

Open [http://localhost:5173](http://localhost:5173) for the dashboard, or [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive API docs.

## Why This Architecture

> *"The best architecture is the one you can change."*

**Adapter pattern for all integrations** — Gmail, Slack, HubSpot, and LiteLLM each sit behind an abstract interface. Swapping Gmail for Outlook, or Slack for Teams, requires implementing one class. Zero changes to business logic. See the [Adapter Extension Guide](docs/adapter-guide.md).

**Celery pipeline, not monolith processing** — Each pipeline stage (ingest → classify → route → sync → draft) runs as an independent Celery task. A failure at stage 3 doesn't roll back stages 1 and 2. Failed stages retry with exponential backoff and land in a specific error state for debugging.

**Type safety at every boundary** — Pydantic models at API boundaries, typed dataclasses at adapter boundaries, and auto-generated TypeScript types for the frontend. No `dict[str, Any]` crossing layer boundaries.

**Redis does three jobs** — Message broker for Celery, classification cache for deduplication, and refresh token store for JWT auth. One dependency, three capabilities.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **API** | FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| **Frontend** | React + Vite + TypeScript |
| **AI/ML** | LiteLLM (OpenAI / Anthropic / Ollama) |
| **Pipeline** | Celery + Redis |
| **Database** | PostgreSQL (JSONB, pg_trgm search) |
| **Integrations** | Gmail API, Slack SDK, HubSpot SDK |
| **Auth** | JWT + bcrypt + Redis refresh tokens |
| **Infra** | Docker Compose (6 services), Alembic migrations |
| **Quality** | pytest, ruff, mypy, GitHub Actions CI/CD |

## Project Structure

```
src/
├── adapters/           # External integrations (adapter pattern)
│   ├── email/          #   Gmail adapter (OAuth2, incremental sync)
│   ├── channel/        #   Slack adapter (Block Kit, async)
│   ├── crm/            #   HubSpot adapter (contacts, deals, activities)
│   └── llm/            #   LiteLLM adapter (7-shape JSON parser)
├── api/                # FastAPI routers + Pydantic schemas
│   ├── routers/        #   10 routers, 48 endpoints
│   └── schemas/        #   Request/response models
├── core/               # Config, security, database, logging
├── models/             # SQLAlchemy ORM (10 models, state machine)
├── services/           # Business logic layer
│   ├── classification.py   # 5-layer defense, heuristic fallback
│   ├── routing.py          # Rule engine, 6 operators
│   ├── draft_generation.py # Context-aware drafts
│   └── crm_sync.py         # Idempotent 6-op chain
├── tasks/              # Celery 5-task pipeline
└── scheduler/          # APScheduler (dedicated container)

frontend/
├── src/
│   ├── pages/          # 12 pages (email browser, analytics, config)
│   ├── components/     # Reusable UI components
│   ├── hooks/          # Custom React hooks
│   └── api/            # Auto-typed API client
```

## Testing

The test suite covers unit, integration, E2E, and contract tests:

```bash
pytest                                    # Unit + API tests (no infra needed)
pytest --run-integration                  # Requires PostgreSQL + Redis
pytest --run-e2e                          # Full pipeline with mock adapters
cd frontend && npm test                   # Frontend component tests
```

**Test philosophy:** Mock adapters implement real ABCs (mypy catches contract violations in tests). E2E tests use Celery eager mode with real database operations. Each pipeline stage is tested independently and as part of the full chain.

## Documentation

- [Deployment Guide](docs/deployment.md) — Production setup, environment variables, troubleshooting
- [Adapter Extension Guide](docs/adapter-guide.md) — How to add new email, channel, CRM, or LLM providers
- [Technical Decisions](docs/DECISIONS.md) — Architecture rationale with alternatives considered
- [API Documentation](http://localhost:8000/docs) — Auto-generated OpenAPI (requires running server)

## Engineering Decisions

A few decisions that shaped the architecture:

- **LiteLLM over direct SDKs** — Unified `completion()` for all providers. When GPT-4o broke our JSON parser, we switched to Claude in one config change. ([Decision log](docs/DECISIONS.md))
- **Celery over async-only** — Professional-grade retry, dead-letter queues, and task monitoring. The pipeline survived a 30-minute Slack outage with zero data loss.
- **PostgreSQL JSONB for LLM output** — Raw LLM responses stored alongside parsed results. When the parser improves, historical emails can be re-classified without re-calling the LLM.
- **5-layer prompt injection defense** — Not just "we sanitize input." Input sanitization → defensive prompt engineering → data delimiters → output validation against DB enums → no tool access during classification.

## Development

```bash
# Backend
pip install -e ".[dev]"
ruff check .              # Lint
ruff format .             # Format
mypy src/                 # Type check
pytest --cov=src          # Tests with coverage

# Frontend
cd frontend
npm install
npm run dev               # Dev server
npm test                  # Vitest
npm run lint              # ESLint
```

## License

[MIT](LICENSE)
