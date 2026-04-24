# Block 19: Deployment & Documentation — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-19-deployment.md`.

## What to build

Docker Compose health checks for all 6 services (pin image versions), structured JSON
logging with `CorrelationIdFilter` + `PiiSanitizingFilter`, complete `.env.example` with
all 60+ Settings fields, deployment guide (`docs/deployment.md`), adapter extensibility
guide (`docs/adapter-guide.md`), and infrastructure tests. This block is **backend + infra
only** — no frontend code changes.

## What already exists (your starting point)

**Infrastructure (DO NOT recreate):**
- `docker-compose.yml`: 6 services defined (db, redis, api, worker, scheduler, frontend)
  - db + redis: have healthchecks (hardcoded intervals, unpinned images)
  - api: has healthcheck (wrong path `/health`, should be `/api/v1/health`)
  - worker: NO healthcheck
  - scheduler: NO healthcheck
  - frontend: NO healthcheck
  - Images unpinned: `postgres:16-alpine`, `redis:7-alpine` (no patch version)
- `Dockerfile`: multi-stage build with `runtime` target
- `Dockerfile.frontend`: multi-stage build with `dev` target

**Logging (partial — needs enhancement):**
- `src/core/logging.py`: EXISTS but minimal — `ConsoleRenderer` only, no JSON output,
  no `PiiSanitizingFilter`, no `CorrelationIdFilter`. Has `configure_logging()` and
  `get_logger()` functions.
- `structlog` already used throughout codebase (all services import `structlog.get_logger`)
- `configure_logging()` is NOT called in any entry point yet

**Correlation IDs:**
- `src/core/correlation.py`: DOES NOT EXIST — must create

**Entry points (where configure_logging() must be called):**
- `src/api/main.py:46-49`: lifespan context manager — add `configure_logging()` in startup
- `src/tasks/celery_app.py:17-47`: `_create_celery_app()` — add worker init signal
- `src/scheduler/main.py:24-73`: `main()` function — add before scheduler.start()

**Config:**
- `src/core/config.py`: 60+ Settings fields already defined, well-organized by section
- Missing from Settings: `LOG_LEVEL`, `LOG_FORMAT` (needed for B19 logging config)

**.env.example (incomplete):**
- EXISTS at `.env.example` with ~30 variables
- Missing ~35 variables from Settings (see delta table below)

**NOT created yet (B19 must create):**
- `src/core/correlation.py` — CorrelationIdContext
- `docker/healthchecks/worker-health.sh` — Celery worker healthcheck script
- `docker/healthchecks/scheduler-health.sh` — Scheduler healthcheck script
- `docker-compose.prod.yml` — Production overrides
- `docs/deployment.md` — Deployment guide
- `docs/adapter-guide.md` — Adapter extensibility guide
- `tests/infrastructure/` — Health check, logging, env parity tests

## CRITICAL: Spec vs. codebase deltas

The B19 spec has 21 amendments. **Follow the codebase, not the original spec text.**

| # | Spec says | Codebase reality | Action |
|---|-----------|-------------------|--------|
| 1 | `src/core/logging.py` + `correlation.py` don't exist | `logging.py` EXISTS (minimal stub) | Enhance existing `logging.py`, create `correlation.py` |
| 2 | `rule_id: int` in PII policy | `RoutingAction.rule_id: UUID \| None` | Use `UUID` in docs |
| 3 | `API_CORS_ALLOWED_ORIGINS` env var | Settings: `cors_origins` → env `CORS_ORIGINS` | Use `CORS_ORIGINS` |
| 4 | `JWT_ACCESS_TOKEN_TTL_SECONDS` | Settings: `jwt_access_ttl_minutes` (minutes, not seconds) | Use `JWT_ACCESS_TTL_MINUTES` |
| 5 | `JWT_REFRESH_TOKEN_TTL_SECONDS` | Settings: `jwt_refresh_ttl_days` (days, not seconds) | Use `JWT_REFRESH_TTL_DAYS` |
| 6 | `LLM_CLASSIFY_MODEL` | Settings: `llm_model_classify` → env `LLM_MODEL_CLASSIFY` | Fix name |
| 7 | `LLM_DRAFT_MODEL` | Settings: `llm_model_draft` → env `LLM_MODEL_DRAFT` | Fix name |
| 8 | `LLM_CLASSIFY_TEMPERATURE` | Settings: `llm_temperature_classify` → env `LLM_TEMPERATURE_CLASSIFY` | Fix name |
| 9 | `LLM_DRAFT_TEMPERATURE` | Settings: `llm_temperature_draft` → env `LLM_TEMPERATURE_DRAFT` | Fix name |
| 10 | `LLM_API_KEY` (single key) | Separate: `openai_api_key`, `anthropic_api_key` | Document both |
| 11 | `HUBSPOT_API_TOKEN` | Settings: `hubspot_access_token` → env `HUBSPOT_ACCESS_TOKEN` | Fix name |
| 12 | `LLM_BODY_TRUNCATION_CHARS` | Settings: `max_body_length` → env `MAX_BODY_LENGTH` | Fix name |
| 13 | `LLM_SNIPPET_LENGTH` | Settings: `snippet_length` → env `SNIPPET_LENGTH` | Fix name |
| 14 | `PIPELINE_POLL_INTERVAL_SECONDS` | Settings: `polling_interval_seconds` → env `POLLING_INTERVAL_SECONDS` | Fix name |
| 15 | `PIPELINE_*_MAX_RETRIES` (per-task) | Single `celery_max_retries: int = 3` for all tasks | Document single `CELERY_MAX_RETRIES` |
| 16 | `ANALYTICS_CSV_CHUNK_SIZE` default `100` | Settings default is `1000` | Fix default |
| 17 | `account_id: UUID` in PII policy | `Email.account: str` (plain string, not UUID) | Fix type |
| 18 | `src.cli create-admin` command | `src/cli` module does NOT exist | Document manual Python REPL alternative |
| 19 | `curl .../api/health` | Actual: `GET /api/v1/health` | Fix path |
| 20 | `EmailAccount` model referenced | No such model — `Email.account` is plain `str` | Fix terminology |
| 21 | ~25 vars in spec | 60+ Settings fields exist | Add ALL to `.env.example` |

## Settings fields — complete inventory

All fields from `src/core/config.py` organized by section. Fields with `...` (no default)
are REQUIRED. Fields with `default=X` are optional.

### Database (REQUIRED)
- `database_url: str` — `...` (no default)
- `database_url_sync: str` — `...` (no default)

### Redis
- `redis_url: str` — `"redis://redis:6379/0"`

### JWT (jwt_secret_key REQUIRED)
- `jwt_secret_key: str` — `...` (no default)
- `jwt_algorithm: str` — `"HS256"`
- `jwt_access_ttl_minutes: int` — `15`
- `jwt_refresh_ttl_days: int` — `7`

### Security
- `bcrypt_rounds: int` — `12`
- `cors_origins: list[str]` — `["http://localhost:5173"]`

### Pipeline
- `polling_interval_seconds: int` — `300`
- `ingestion_batch_size: int` — `50`
- `max_body_length: int` — `4000`
- `snippet_length: int` — `200`
- `data_retention_days: int` — `90`

### LLM
- `llm_model_classify: str` — `"gpt-4o-mini"`
- `llm_model_draft: str` — `"gpt-4o"`
- `llm_temperature_classify: float` — `0.1`
- `llm_temperature_draft: float` — `0.7`
- `openai_api_key: str` — `""`
- `anthropic_api_key: str` — `""`
- `llm_fallback_model: str` — `"gpt-3.5-turbo"`
- `llm_timeout_seconds: int` — `30`
- `llm_classify_max_tokens: int` — `500`
- `llm_draft_max_tokens: int` — `2000`
- `llm_base_url: str` — `""`

### Ingestion lock
- `ingestion_lock_ttl_seconds: int` — `300`
- `ingestion_lock_key_prefix: str` — `"mailwise:ingest:lock"`

### Classification
- `classify_max_few_shot_examples: int` — `10`
- `classify_feedback_snippet_chars: int` — `200`
- `classify_internal_domains: str` — `""`

### Celery
- `celery_max_retries: int` — `3`
- `celery_backoff_base: int` — `60`
- `celery_broker_url: str` — `"redis://redis:6379/0"`
- `celery_result_backend: str` — `"redis://redis:6379/1"`
- `celery_result_expires: int` — `3600`

### Pipeline & Scheduler
- `pipeline_scheduler_lock_key_prefix: str` — `"mailwise:scheduler:lock"`
- `pipeline_scheduler_lock_ttl_seconds: int` — `300`

### Gmail OAuth
- `gmail_client_id: str` — `""`
- `gmail_client_secret: str` — `""`
- `gmail_redirect_uri: str` — `"http://localhost:8000/api/v1/auth/gmail/callback"`
- `gmail_max_results: int` — `100`
- `gmail_credentials_file: str` — `"secrets/gmail_credentials.json"`
- `gmail_token_file: str` — `"secrets/gmail_token.json"`

### Slack
- `slack_bot_token: str` — `""`
- `slack_signing_secret: str` — `""`

### Channel adapter
- `channel_snippet_length: int` — `150`
- `channel_subject_max_length: int` — `100`
- `channel_slack_timeout_seconds: int` — `10`
- `channel_destinations_page_size: int` — `200`

### Routing
- `routing_vip_senders: str` — `""`
- `routing_dashboard_base_url: str` — `"http://localhost:3000"`
- `routing_snippet_length: int` — `150`

### HubSpot
- `hubspot_access_token: str` — `""`
- `hubspot_rate_limit_per_10s: int` — `100`
- `hubspot_activity_snippet_length: int` — `200`
- `hubspot_auto_create_contacts: bool` — `False`
- `hubspot_default_lead_status: str` — `"NEW"`
- `hubspot_api_timeout_seconds: int` — `15`

### CRM Sync
- `crm_sync_retry_max: int` — `3`
- `crm_sync_backoff_base_seconds: int` — `60`

### Draft Generation
- `draft_push_to_gmail: bool` — `False`
- `draft_org_system_prompt: str` — `""`
- `draft_org_tone: str` — `"professional"`
- `draft_org_signature: str` — `""`
- `draft_org_prohibited_language: str` — `""`
- `draft_generation_retry_max: int` — `2`

### API
- `api_health_adapter_timeout_ms: int` — `200`
- `app_version: str` — `"0.1.0"`

### Analytics
- `analytics_max_date_range_days: int` — `365`
- `analytics_csv_chunk_size: int` — `1000`
- `analytics_default_timezone: str` — `"UTC"`

### NOT yet in Settings (B19 must add)
- `log_level: str` — `"INFO"` (for `LOG_LEVEL` env var)
- `log_format: str` — `"json"` (for `LOG_FORMAT` env var)

## Current docker-compose.yml — exact state

```yaml
services:
  db:
    image: postgres:16-alpine           # UNPINNED — needs patch version
    healthcheck: yes (hardcoded intervals)
  redis:
    image: redis:7-alpine               # UNPINNED — needs patch version
    healthcheck: yes (hardcoded intervals)
  api:
    build: Dockerfile (target: runtime)
    healthcheck: yes (WRONG path: /health, should be /api/v1/health)
    depends_on: db (healthy), redis (healthy)
  worker:
    build: Dockerfile (target: runtime)
    command: celery -A src.tasks.celery_app worker --loglevel=info
    healthcheck: NONE                    # Must add
    depends_on: db (healthy), redis (healthy)
  scheduler:
    build: Dockerfile (target: runtime)
    command: python -m src.tasks.scheduler  # WRONG: should be src.scheduler
    healthcheck: NONE                    # Must add
    depends_on: db (healthy), redis (healthy), api (healthy)
  frontend:
    build: Dockerfile.frontend (target: dev)
    healthcheck: NONE                    # Must add
    depends_on: api (healthy)
```

**Known issues to fix:**
1. `scheduler.command`: `python -m src.tasks.scheduler` → `python -m src.scheduler`
   (scheduler is at `src/scheduler/main.py`, not `src/tasks/scheduler`)
2. `api.healthcheck.test`: path is `/health` but actual endpoint is `/api/v1/health`
3. Images unpinned — need exact patch versions per Cat 10
4. Health check intervals hardcoded — need `${HEALTHCHECK_INTERVAL:-30s}` pattern per Cat 8
5. Worker + scheduler + frontend missing healthchecks entirely

## Existing logging.py — what to enhance

Current state (`src/core/logging.py`):
```python
def configure_logging(log_level: str = "INFO") -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),  # MUST change to JSONRenderer for prod
        ],
        ...
    )
```

**What to add:**
1. `CorrelationIdFilter` processor — injects `correlation_id` from `ContextVar`
2. `PiiSanitizingFilter` processor — last-line defense for PII fields
3. Conditional renderer: `JSONRenderer` when `LOG_FORMAT=json`, `ConsoleRenderer` when `LOG_FORMAT=text`
4. Call `configure_logging()` in all 3 entry points

## Entry points — where to call configure_logging()

### src/api/main.py (lifespan)
```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from src.core.logging import configure_logging
    configure_logging()  # ADD THIS
    yield
    await close_redis()
```

### src/tasks/celery_app.py (worker init signal)
```python
from celery.signals import worker_init

@worker_init.connect
def on_worker_init(**kwargs):
    from src.core.logging import configure_logging
    configure_logging()
```

### src/scheduler/main.py (before scheduler.start)
```python
async def main() -> None:
    from src.core.logging import configure_logging
    configure_logging()  # ADD before scheduler.start()
    settings = get_settings()
    ...
```

## .env.example — variables missing (must add)

Currently has ~30 vars. The following are in Settings but NOT in `.env.example`:

```
# LLM (missing)
LLM_FALLBACK_MODEL, LLM_TIMEOUT_SECONDS, LLM_CLASSIFY_MAX_TOKENS,
LLM_DRAFT_MAX_TOKENS, LLM_BASE_URL

# Ingestion lock (missing entirely)
INGESTION_LOCK_TTL_SECONDS, INGESTION_LOCK_KEY_PREFIX

# Classification (missing entirely)
CLASSIFY_MAX_FEW_SHOT_EXAMPLES, CLASSIFY_FEEDBACK_SNIPPET_CHARS,
CLASSIFY_INTERNAL_DOMAINS

# Celery (missing)
CELERY_BROKER_URL, CELERY_RESULT_BACKEND, CELERY_RESULT_EXPIRES

# Pipeline & Scheduler (missing entirely)
PIPELINE_SCHEDULER_LOCK_KEY_PREFIX, PIPELINE_SCHEDULER_LOCK_TTL_SECONDS

# Gmail (missing)
GMAIL_MAX_RESULTS, GMAIL_CREDENTIALS_FILE, GMAIL_TOKEN_FILE

# Channel adapter (missing entirely)
CHANNEL_SNIPPET_LENGTH, CHANNEL_SUBJECT_MAX_LENGTH,
CHANNEL_SLACK_TIMEOUT_SECONDS, CHANNEL_DESTINATIONS_PAGE_SIZE

# Routing (missing entirely)
ROUTING_VIP_SENDERS, ROUTING_DASHBOARD_BASE_URL, ROUTING_SNIPPET_LENGTH

# HubSpot (missing)
HUBSPOT_RATE_LIMIT_PER_10S, HUBSPOT_ACTIVITY_SNIPPET_LENGTH,
HUBSPOT_AUTO_CREATE_CONTACTS, HUBSPOT_DEFAULT_LEAD_STATUS,
HUBSPOT_API_TIMEOUT_SECONDS

# CRM Sync (missing entirely)
CRM_SYNC_RETRY_MAX, CRM_SYNC_BACKOFF_BASE_SECONDS

# Draft Generation (missing entirely)
DRAFT_PUSH_TO_GMAIL, DRAFT_ORG_SYSTEM_PROMPT, DRAFT_ORG_TONE,
DRAFT_ORG_SIGNATURE, DRAFT_ORG_PROHIBITED_LANGUAGE,
DRAFT_GENERATION_RETRY_MAX

# API (missing entirely)
API_HEALTH_ADAPTER_TIMEOUT_MS, APP_VERSION

# Analytics (missing entirely)
ANALYTICS_MAX_DATE_RANGE_DAYS, ANALYTICS_CSV_CHUNK_SIZE,
ANALYTICS_DEFAULT_TIMEZONE

# Logging (NEW — add to Settings first)
LOG_LEVEL, LOG_FORMAT
```

## Files to create

| File | Purpose |
|------|---------|
| `src/core/correlation.py` | `CorrelationIdContext` via `contextvars.ContextVar` |
| `docker/healthchecks/worker-health.sh` | Celery worker healthcheck (`celery inspect ping`) |
| `docker/healthchecks/scheduler-health.sh` | Scheduler healthcheck (process alive + Redis lock TTL) |
| `docker-compose.prod.yml` | Production overrides (Nginx, secrets, restart policies) |
| `docs/deployment.md` | Full deployment guide (6 sections per spec) |
| `docs/adapter-guide.md` | Adapter extensibility guide (4 families, 5-step pattern) |
| `tests/infrastructure/__init__.py` | Package marker |
| `tests/infrastructure/test_health_checks.py` | Docker health check tests (`@pytest.mark.docker`) |
| `tests/infrastructure/test_logging.py` | JSON structured logging tests |
| `tests/infrastructure/test_env_example.py` | `.env.example` ↔ Settings parity test |

## Files to modify

| File | Change |
|------|--------|
| `src/core/logging.py` | Add CorrelationIdFilter, PiiSanitizingFilter, JSONRenderer, LOG_FORMAT toggle |
| `src/core/config.py` | Add `log_level` and `log_format` fields to Settings |
| `src/api/main.py` | Call `configure_logging()` in lifespan startup |
| `src/tasks/celery_app.py` | Add `worker_init` signal → `configure_logging()` |
| `src/scheduler/main.py` | Call `configure_logging()` before scheduler.start() |
| `docker-compose.yml` | Pin images, fix healthchecks, add missing healthchecks, parameterize intervals |
| `.env.example` | Add all ~35 missing variables with descriptions |

## Adapter ABCs — reference for adapter-guide.md

All 4 adapter families with their ABCs (documented in B18 handoff — same):
- `EmailAdapter` (`src/adapters/email/base.py`): 7 methods (connect, fetch, mark, create_draft, labels, test_connection)
- `LLMAdapter` (`src/adapters/llm/base.py`): 3 async methods (classify, generate_draft, test_connection)
- `ChannelAdapter` (`src/adapters/channel/base.py`): 4 async methods (connect, send_notification, test_connection, get_destinations)
- `CRMAdapter` (`src/adapters/crm/base.py`): 7 async methods (connect, lookup, create, log_activity, create_lead, update_field, test_connection)

## Quality gates (ordered)

```bash
# 1. Type safety
mypy src/core/logging.py src/core/correlation.py

# 2. Lint
ruff check src/core/ && ruff format --check src/core/

# 3. Env parity test
pytest tests/infrastructure/test_env_example.py -v

# 4. Logging tests
pytest tests/infrastructure/test_logging.py -v

# 5. Docker build
docker compose build

# 6. Docker up + healthy
docker compose up -d && docker compose ps  # all 6 healthy

# 7. Health check tests (requires Docker)
pytest tests/infrastructure/test_health_checks.py -v --docker

# 8. Docs check
bash scripts/validate-docs.sh

# 9. Cat 10 audit — all images pinned
grep "image:" docker-compose.yml | grep -vE "[0-9]+\.[0-9]+\.[0-9]"
# Expected: empty

# 10. Cat 8 audit — no hardcoded intervals
grep -E "interval:|timeout:|retries:" docker-compose.yml | grep -v "\${"
# Expected: empty

# 11. configure_logging() in all 3 entry points
grep -rn "configure_logging()" src/api/main.py src/tasks/celery_app.py src/scheduler/main.py
# Expected: 3 matches
```

## Pre-implementation decisions needed

### 1. PiiSanitizingFilter approach
- **Option A**: structlog processor that scans log event keys for prohibited names
  (subject, sender_email, body_plain, body_html, sender_name) and replaces values with
  `[REDACTED]`. Risk: false positives on keys containing "subject" in non-PII context.
- **Option B**: structlog processor that only scans specific event dict keys (not nested).
  Safer — PII fields have unique names in the ORM, unlikely collision.
- **Recommended**: Option B — scan top-level event keys only.

### 2. Docker image versions
Look up latest stable patch versions at implementation time:
- Python: `python:3.12.X-slim-bookworm`
- Node: `node:20.X-alpine3.21`
- PostgreSQL: `postgres:16.X-alpine`
- Redis: `redis:7.4.X-alpine`

### 3. src/cli module
The spec references `src.cli create-admin` but no CLI module exists. Options:
- **Option A**: Create minimal `src/cli.py` with click/typer (new dependency)
- **Option B**: Document a Python REPL one-liner in deployment guide
- **Recommended**: Option B — avoids new dependency for single command
