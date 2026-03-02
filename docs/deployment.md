# Deployment Guide — mailwise

## 1. Prerequisites

- Docker >= 24.0
- Docker Compose >= 2.20
- Git
- API keys:
  - Gmail OAuth2 credentials (Google Cloud Console — see section 4)
  - OpenAI or Anthropic API key (LLM classification and draft generation)
  - Slack Bot Token (optional — routing notifications)
  - HubSpot Private App Token (optional — CRM sync)

## 2. Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/your-org/mailwise.git
cd mailwise

# 2. Copy environment template
cp .env.example .env

# 3. Edit .env — fill in at minimum:
#    DATABASE_URL, DATABASE_URL_SYNC, JWT_SECRET_KEY, OPENAI_API_KEY or ANTHROPIC_API_KEY
#    (see Section 3 for full reference)
$EDITOR .env

# 4. Start all services
docker compose up -d

# 5. Verify health
curl http://localhost:8000/api/v1/health
```

Services start in dependency order: `db` and `redis` first, then `api`, then `worker`, `scheduler`, and `frontend`. Allow ~60 seconds on first run while the API container pulls dependencies and runs Alembic migrations.

Expected healthy output from `docker compose ps` (base compose — db/redis have no host ports):
```
NAME        STATUS                   PORTS
db          Up (healthy)
redis       Up (healthy)
api         Up (healthy)             0.0.0.0:8000->8000/tcp
worker      Up (healthy)
scheduler   Up (healthy)
frontend    Up (healthy)             0.0.0.0:5173->5173/tcp
```

With the dev overlay (`docker compose -f docker-compose.yml -f docker-compose.dev.yml ps`):
```
NAME        STATUS                   PORTS
db          Up (healthy)             0.0.0.0:5432->5432/tcp
redis       Up (healthy)             0.0.0.0:6379->6379/tcp
```

## 3. Environment Variables

All variables are read from `.env` at container start via `pydantic-settings`. Variables marked **REQUIRED** have no default and will cause startup failure if missing.

### Database

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | **REQUIRED** | — | PostgreSQL async URL: `postgresql+asyncpg://user:pass@db:5432/mailwise` |
| `DATABASE_URL_SYNC` | **REQUIRED** | — | PostgreSQL sync URL: `postgresql+psycopg2://user:pass@db:5432/mailwise` |
| `POSTGRES_USER` | No | `mailwise` | Docker Compose db service user |
| `POSTGRES_PASSWORD` | No | `password` | Docker Compose db service password — change in production |
| `POSTGRES_DB` | No | `mailwise` | Docker Compose db service database name |

### Redis

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDIS_URL` | No | `redis://redis:6379/0` | Redis connection URL (used by API for refresh tokens) |
| `CELERY_BROKER_URL` | No | `redis://redis:6379/0` | Celery broker |
| `CELERY_RESULT_BACKEND` | No | `redis://redis:6379/1` | Celery result backend (separate DB index) |
| `CELERY_RESULT_EXPIRES` | No | `3600` | Result expiry in seconds |

### Authentication

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JWT_SECRET_KEY` | **REQUIRED** | — | JWT signing key. Generate: `openssl rand -hex 32` |
| `JWT_ALGORITHM` | No | `HS256` | JWT algorithm |
| `JWT_ACCESS_TTL_MINUTES` | No | `15` | Access token lifetime (minutes). Cat 8: load-bearing |
| `JWT_REFRESH_TTL_DAYS` | No | `7` | Refresh token lifetime (days) |
| `BCRYPT_ROUNDS` | No | `12` | bcrypt work factor. Cat 8: load-bearing. Too low: brute-force risk. Too high: login >1s |
| `CORS_ORIGINS` | No | `["http://localhost:5173"]` | JSON array of allowed CORS origins. No default in production — set explicitly |

### LLM

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | No* | `""` | OpenAI API key. Required if using OpenAI models |
| `ANTHROPIC_API_KEY` | No* | `""` | Anthropic API key. Required if using Anthropic models |
| `LLM_MODEL_CLASSIFY` | No | `gpt-4o-mini` | Model for classification (cheap, temp 0.1) |
| `LLM_MODEL_DRAFT` | No | `gpt-4o` | Model for draft generation (capable, temp 0.7) |
| `LLM_FALLBACK_MODEL` | No | `gpt-3.5-turbo` | Fallback model on primary failure |
| `LLM_TEMPERATURE_CLASSIFY` | No | `0.1` | Cat 8: high temp causes inconsistent classifications |
| `LLM_TEMPERATURE_DRAFT` | No | `0.7` | Cat 8: low temp produces robotic drafts |
| `LLM_TIMEOUT_SECONDS` | No | `30` | LLM API call timeout |
| `LLM_CLASSIFY_MAX_TOKENS` | No | `500` | Max tokens for classification response |
| `LLM_DRAFT_MAX_TOKENS` | No | `2000` | Max tokens for draft response |
| `LLM_BASE_URL` | No | `""` | Custom base URL (for Ollama or proxies) |

\* At least one LLM API key must be provided for the pipeline to function.

### Gmail

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GMAIL_CLIENT_ID` | No* | `""` | OAuth2 client ID from Google Cloud Console |
| `GMAIL_CLIENT_SECRET` | No* | `""` | OAuth2 client secret |
| `GMAIL_REDIRECT_URI` | No | `http://localhost:8000/api/v1/auth/gmail/callback` | OAuth2 redirect URI |
| `GMAIL_MAX_RESULTS` | No | `100` | Max messages per API call |
| `GMAIL_CREDENTIALS_FILE` | No | `secrets/gmail_credentials.json` | Path to OAuth2 credentials file |
| `GMAIL_TOKEN_FILE` | No | `secrets/gmail_token.json` | Path to OAuth2 token file |

\* Required for Gmail ingestion.

### Slack

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SLACK_BOT_TOKEN` | No | `""` | Bot token (`xoxb-...`). Required for Slack routing |
| `SLACK_SIGNING_SECRET` | No | `""` | Signing secret for request verification |
| `CHANNEL_SNIPPET_LENGTH` | No | `150` | Message preview length in Slack notifications |
| `CHANNEL_SLACK_TIMEOUT_SECONDS` | No | `10` | Slack API call timeout |

### HubSpot

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `HUBSPOT_ACCESS_TOKEN` | No | `""` | Private App Token. Required for CRM sync |
| `HUBSPOT_AUTO_CREATE_CONTACTS` | No | `false` | Auto-create contacts for unknown senders |
| `HUBSPOT_DEFAULT_LEAD_STATUS` | No | `NEW` | Default status for created deals |
| `HUBSPOT_API_TIMEOUT_SECONDS` | No | `15` | HubSpot API call timeout |
| `HUBSPOT_RATE_LIMIT_PER_10S` | No | `100` | Rate limit ceiling (requests per 10 seconds) |

### Pipeline

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `POLLING_INTERVAL_SECONDS` | No | `300` | Gmail polling frequency. Cat 8: too low = Gmail rate limit |
| `INGESTION_BATCH_SIZE` | No | `50` | Emails per ingestion run. Cat 8: too high = LLM timeout |
| `MAX_BODY_LENGTH` | No | `4000` | Email body truncation before LLM. Cat 8: affects LLM context |
| `SNIPPET_LENGTH` | No | `200` | Preview snippet length for UI and logs |
| `DATA_RETENTION_DAYS` | No | `90` | Email retention period before cleanup |
| `CELERY_MAX_RETRIES` | No | `3` | Pipeline task retry limit |
| `CELERY_BACKOFF_BASE` | No | `60` | Retry backoff base (seconds, exponential) |

### Draft Generation

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DRAFT_PUSH_TO_GMAIL` | No | `false` | Push generated drafts to Gmail. Enable after testing |
| `DRAFT_ORG_SYSTEM_PROMPT` | No | `""` | Organization-level system prompt appended to all drafts |
| `DRAFT_ORG_TONE` | No | `professional` | Default tone: `professional`, `friendly`, `formal` |
| `DRAFT_ORG_SIGNATURE` | No | `""` | Email signature appended to drafts |
| `DRAFT_ORG_PROHIBITED_LANGUAGE` | No | `""` | Comma-separated prohibited terms |

### Logging

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LOG_LEVEL` | No | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | No | `json` | Log format: `json` (production) or `console` (development) |

## 4. First-time Setup

### Step 1: Create admin user

No CLI module exists. Use the Python REPL inside the running `api` container:

```bash
docker compose exec api python -c "
import asyncio
from src.core.database import get_async_session_factory
from src.services.auth_service import AuthService

async def create_admin():
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = AuthService(session)
        user = await service.create_user(
            email='admin@example.com',
            password='change-me-immediately',
            role='admin',
        )
        await session.commit()
        print(f'Admin created: {user.id}')

asyncio.run(create_admin())
"
```

The exact `AuthService` method signature may vary slightly — inspect `src/services/auth_service.py` if the call fails.

### Step 2: Configure integrations

Log in to the dashboard at `http://localhost:5173` with the admin credentials, then navigate to Settings > Integrations to configure Gmail, Slack, and HubSpot connections.

### Step 3: Create initial categories

Navigate to Settings > Classification to define at least one classification category. Categories are required before the pipeline can classify emails.

### Step 4: Create a routing rule

Navigate to Settings > Routing Rules and create a default rule that maps at least one category to a destination. Without a routing rule, classified emails will remain in the `CLASSIFIED` state.

### Step 5: Verify end-to-end

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Confirm all adapters connected
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/health/detailed
```

### Gmail OAuth Setup

1. Create a project in Google Cloud Console
2. Enable the Gmail API
3. Create OAuth 2.0 credentials (Desktop app type for local dev)
4. Download `credentials.json` and place it at `secrets/gmail_credentials.json`
5. Set `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET` in `.env`
6. On first run, navigate to the OAuth callback URL to authorize access

Minimum required Gmail scopes:
- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/gmail.modify`
- `https://www.googleapis.com/auth/gmail.compose`

## 5. Production Considerations

### Compose override

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The base `docker-compose.yml` does not expose `ports:` for `db` or `redis` — they are internal to the Docker network. The dev overlay (`docker-compose.dev.yml`) adds host port bindings for local tool access. In production, do not use the dev overlay.

### HTTPS

Deploy behind a reverse proxy (Nginx, Caddy, Traefik). Configure `CORS_ORIGINS` with your production domain — there is no default in production builds and startup will fail if not set.

### Secrets management

Do not use `.env` files in production. Use your platform's secret management:
- Docker Swarm: `docker secret`
- Kubernetes: `kubectl create secret`
- Cloud: AWS Secrets Manager, GCP Secret Manager, Azure Key Vault

### Database backups

```bash
# Manual backup
docker compose exec db pg_dump -U mailwise mailwise > backup-$(date +%Y%m%d).sql

# Restore
docker compose exec -T db psql -U mailwise mailwise < backup-20260101.sql
```

### Horizontal scaling

Workers scale independently:

```bash
docker compose up -d --scale worker=3
```

Only one `scheduler` instance should run at all times — the Redis lock prevents duplicate polling, but multiple scheduler containers waste resources.

### Tested image combination

| Image | Version |
|-------|---------|
| `postgres` | `16.6-alpine` |
| `redis` | `7.4-alpine` |
| `python` | `3.12.9-slim-bookworm` |
| `node` | `20.18-alpine3.21` |

### Monitoring

- Primary health endpoint: `GET /api/v1/health` (checks db + redis + adapters)
- Structured JSON logs via structlog — pipe to your log aggregator
- `LOG_LEVEL=DEBUG` for verbose pipeline tracing (do not use in production)

## 6. Troubleshooting

| Symptom | Likely Cause | Solution |
|---------|-------------|----------|
| `api` container exits immediately | Missing required env var (`DATABASE_URL`, `DATABASE_URL_SYNC`, or `JWT_SECRET_KEY`) | Check `docker compose logs api` for the pydantic `ValidationError` message |
| `api` health check fails after 60s | Database migration failed | Run `docker compose logs api` — look for Alembic errors. Check `DATABASE_URL` matches `POSTGRES_USER`/`POSTGRES_PASSWORD` |
| `worker` exits with `Connection refused` | Redis not ready | Run `docker compose logs redis`. Ensure `db` and `redis` are healthy before `worker` starts |
| `scheduler` exits immediately | `api` not yet healthy | Scheduler depends on `api: condition: service_healthy`. Allow 60–90s on first start |
| Gmail ingestion does nothing | OAuth token expired or not authorized | Re-run the OAuth flow. Check `secrets/gmail_token.json` exists and is valid |
| Classification stuck in `FETCHED` | No LLM API key provided | Set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` in `.env` and restart |
| Emails stay in `CLASSIFIED` | No routing rule matches | Add a routing rule in Settings > Routing Rules |
| Slack notifications not delivered | `SLACK_BOT_TOKEN` empty or bot not in channel | Verify token starts with `xoxb-`. Add the bot to the destination channel |
| HubSpot sync failing | Token expired or insufficient scopes | Regenerate Private App Token. Required scopes: `crm.objects.contacts.write`, `crm.objects.deals.write` |
| `CORS_ORIGINS` 403 errors | Frontend origin not in allowed list | Update `CORS_ORIGINS` in `.env` to include your frontend URL, e.g. `["https://app.example.com"]` |
| High LLM latency / timeouts | `LLM_TIMEOUT_SECONDS` too low for chosen model | Increase to 60s for GPT-4-class models. Consider `LLM_MODEL_CLASSIFY=gpt-4o-mini` for speed |
| `bcrypt` ImportError on startup | Dependency conflict | Ensure `bcrypt>=4.0,<5` is in `pyproject.toml`. Do NOT install `passlib[bcrypt]` |
