# Block 12: Pipeline & Scheduler — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-12-pipeline.md`.

## What to build

`src/tasks/` — Celery app config, typed result dataclasses, pipeline orchestration (5 tasks + `run_pipeline`). `src/scheduler/` — APScheduler entry point + poll job with Redis lock. Each task commits independently (D13); results stored in DB, NOT via Celery result backend.

### Files to create

| File | Purpose |
|------|---------|
| `src/tasks/celery_app.py` | Celery app instance, broker Redis/0, backend Redis/1, JSON serializer, UTC timezone |
| `src/tasks/result_types.py` | 5 frozen dataclasses: `IngestResult`, `ClassifyResult`, `RouteResult`, `CRMSyncTaskResult`, `DraftTaskResult` |
| `src/tasks/pipeline.py` | `run_pipeline()` + 5 Celery task definitions (ingest → classify → route → crm_sync → draft) |
| `src/scheduler/__init__.py` | Empty |
| `src/scheduler/main.py` | APScheduler entry point, `lock_ttl >= poll_interval` assertion |
| `src/scheduler/jobs.py` | `poll_email_accounts_job`: Redis lock per account, enqueue `ingest_task` |
| `tests/tasks/test_pipeline_result_types.py` | Frozen dataclass validation, no `Any` fields |
| `tests/tasks/test_pipeline_chain.py` | Full chain with mocked services |
| `tests/tasks/test_pipeline_partial_failure.py` | Failure per stage preserves prior state |
| `tests/scheduler/test_poll_job.py` | Lock prevents double-poll, lock released on error |
| `tests/scheduler/test_scheduler_lock.py` | Redis lock acquisition/expiry/crash-safety |

### Files to modify

| File | Change |
|------|--------|
| `src/core/config.py` | Add pipeline/scheduler settings (see Config section) |

## CRITICAL: Architecture decisions from spec

| Decision | Details |
|----------|---------|
| `run_pipeline` is NOT a Celery task | Plain Python function, enqueues `classify_task.delay(email_id)` |
| No `celery.canvas.chain` with `link` | Each task calls `next_task.delay()` explicitly after successful commit |
| Bifurcation in `route_task` | `route_task` decides to call `crm_sync_task.delay()` and/or `draft_task.delay()` conditionally |
| Broker Redis/0, Backend Redis/1 | Separate DB indices for broker and result backend |
| `CELERY_RESULT_EXPIRES=3600` | Business results go to DB, not result backend |
| `AsyncResult.get()` PROHIBITED | Returns `Any` — all results via DB/typed dataclasses |
| Dual lock: scheduler + IngestionService | Scheduler lock = producer-side, IngestionService lock = consumer-side |

## Existing task files — actual signatures

### `src/tasks/ingestion_task.py`

```python
def ingest_emails_task(account_id: str, since_iso: str) -> None:
    """No self parameter — not bind=True. B12 registers with Celery decorator."""

async def _run_ingestion(account_id: str, since: datetime) -> IngestionBatchResult:
    """Constructs Redis client, EmailAdapter, IngestionService, calls ingest_batch()."""
```

**Note:** This task does NOT use `self` / `bind=True`. No retry logic — B12 may need to add it.

### `src/tasks/crm_sync_task.py`

```python
def crm_sync_task(self: object, email_id: str) -> None:
    """bind=True pattern — self enables task.retry()."""

async def _run_crm_sync(task: object, email_id_str: str) -> None:
    """Loads email, builds CRMSyncRequest, calls service.sync(), manages state transitions."""
```

**Retry patterns:**
- `CRMAuthError` → NO retry (transition to `CRM_SYNC_FAILED`, commit, return)
- `CRMRateLimitError` → `task.retry(exc=exc, countdown=countdown)` from exc
- `Exception` → `task.retry(exc=exc)` from exc

### `src/tasks/draft_generation_task.py`

```python
def draft_generation_task(self: object, email_id: str) -> None:
    """bind=True pattern — self enables task.retry()."""

async def _run_draft_generation(task: object, email_id_str: str) -> None:
    """Loads email, builds DraftRequest, calls service.generate()."""
```

**Retry patterns:**
- `LLMRateLimitError` → `task.retry(exc=exc, countdown=retry_after_seconds or 60)` from exc
- `Exception` → `task.retry(exc=exc)` from exc

## Service constructors — actual signatures (from codebase)

```python
# src/services/ingestion.py
class IngestionService:
    def __init__(self, *, adapter: EmailAdapter, session: AsyncSession,
                 redis: Redis, settings: Settings) -> None: ...
    async def ingest_batch(self, account_id: str, *, since: datetime) -> IngestionBatchResult: ...

# src/services/classification.py
class ClassificationService:
    def __init__(self, *, llm_adapter: LLMAdapter, settings: Settings) -> None: ...
    async def classify_email(self, email_id: uuid.UUID, db: AsyncSession) -> ClassificationServiceResult: ...

# src/services/routing.py
class RoutingService:
    def __init__(self, *, channel_adapters: dict[str, ChannelAdapter], settings: Settings) -> None: ...
    async def route(self, email_id: uuid.UUID, db: AsyncSession) -> RoutingResult: ...

# src/services/crm_sync.py
class CRMSyncService:
    def __init__(self, *, crm_adapter: CRMAdapter, config: CRMSyncConfig) -> None: ...
    async def sync(self, request: CRMSyncRequest, db: AsyncSession) -> CRMSyncResult: ...

# src/services/draft_generation.py
class DraftGenerationService:
    def __init__(self, *, llm_adapter: LLMAdapter, email_adapter: EmailAdapter,
                 config: DraftGenerationConfig) -> None: ...
    async def generate(self, request: DraftRequest, db: AsyncSession) -> DraftResult: ...
```

## State machine — pipeline path (from `src/models/email.py`)

```python
# Happy path through pipeline:
FETCHED → SANITIZED → CLASSIFIED → ROUTED → CRM_SYNCED → DRAFT_GENERATED → COMPLETED

# Each task's precondition → postcondition:
ingest_task:     FETCHED → SANITIZED        (handled by IngestionService)
classify_task:   SANITIZED → CLASSIFIED     (or CLASSIFICATION_FAILED)
route_task:      CLASSIFIED → ROUTED        (or ROUTING_FAILED)
crm_sync_task:   ROUTED → CRM_SYNCED        (or CRM_SYNC_FAILED)
draft_task:      CRM_SYNCED → DRAFT_GENERATED (or DRAFT_FAILED)

# Recovery paths (back to precondition for retry):
CLASSIFICATION_FAILED → SANITIZED
ROUTING_FAILED → CLASSIFIED
CRM_SYNC_FAILED → ROUTED
DRAFT_FAILED → CRM_SYNCED
```

**Use `email.transition_to(new_state)` — never direct assignment.**

## Database session factories (from `src/core/database.py`)

```python
AsyncSessionLocal: async_sessionmaker[AsyncSession]  # For FastAPI + async tasks
SyncSessionLocal: sessionmaker[Session]              # For Celery sync tasks

# Async usage (current pattern in all task files):
async with AsyncSessionLocal() as db:
    result = await db.execute(select(Email).where(Email.id == email_id))

# Sync usage (B12 may use for pipeline.py if not using asyncio.run):
with get_sync_db() as db:
    email = db.get(Email, email_id)
```

**Note:** All existing tasks use `AsyncSessionLocal` via `asyncio.run()` bridge. B12 should follow the same pattern for consistency.

## Redis client (from `src/adapters/redis_client.py`)

```python
# For task usage (ingestion pattern):
from redis.asyncio import Redis
redis = Redis.from_url(settings.redis_url)
try:
    # use redis...
finally:
    await redis.aclose()

# For scheduler lock:
acquired = await redis.set(lock_key, "1", nx=True, ex=lock_ttl_seconds)
# acquired is bool — True if lock was set, False if already held
await redis.delete(lock_key)  # release
```

## Config settings — what exists vs what to add

### Already in `config.py` (reuse — do NOT add duplicates)

```python
redis_url: str = Field(default="redis://redis:6379/0")
polling_interval_seconds: int = Field(default=300)
celery_max_retries: int = Field(default=3)
celery_backoff_base: int = Field(default=60)
ingestion_lock_ttl_seconds: int = Field(default=300)
ingestion_lock_key_prefix: str = Field(default="mailwise:ingest:lock")
```

### To ADD to `config.py`

```python
# Pipeline & Scheduler (Cat 8: configurable defaults)
celery_broker_url: str = Field(default="redis://redis:6379/0")
celery_result_backend: str = Field(default="redis://redis:6379/1")
celery_result_expires: int = Field(default=3600)
pipeline_scheduler_lock_key_prefix: str = Field(default="mailwise:scheduler:lock")
pipeline_scheduler_lock_ttl_seconds: int = Field(default=300)
```

**Note:** `polling_interval_seconds` already exists (default=300). Per-task max_retries can reuse `celery_max_retries` or be separated per spec.

## Pipeline chain architecture

```
[scheduler] → ingest_task(account_id)
                   |
             classify_task(email_id)     ← enqueued by ingest_task on success
                   |
             route_task(email_id)        ← enqueued by classify_task on success
                   |
         +---------+---------+
         |                   |
   crm_sync_task        draft_task       ← both conditional; route_task decides
   (if rule says so)   (if rule says so)
```

**Each task calls `next_task.delay(email_id)` after successful commit — NOT via Celery `link`.**

**Bifurcation in `route_task`:** After routing completes, inspect `RoutingResult.actions` for `crm_sync`/`generate_draft` flags and call `.delay()` conditionally.

## Exception strategy (per task)

| Task | Retry exceptions | No-retry exceptions | State on failure |
|------|-----------------|--------------------|--------------------|
| `ingest_task` | `Exception` (top-level) | Email not found → log+return | N/A (batch) |
| `classify_task` | `LLMRateLimitError`, `Exception` | Email not found → log+return | `CLASSIFICATION_FAILED` |
| `route_task` | `Exception` | Email not found → log+return | `ROUTING_FAILED` |
| `crm_sync_task` | `CRMRateLimitError`, `Exception` | `CRMAuthError` → no retry | `CRM_SYNC_FAILED` |
| `draft_task` | `LLMRateLimitError`, `Exception` | Email not found → log+return | `DRAFT_FAILED` |

**D7:** Top-level `except Exception` in each task is the ONLY place bare except is permitted.

## Result types — frozen dataclasses (NOT Pydantic)

```python
# src/tasks/result_types.py
from dataclasses import dataclass
import uuid

@dataclass(frozen=True)
class IngestResult:
    account_id: str
    emails_fetched: int
    emails_skipped: int
    emails_failed: int

@dataclass(frozen=True)
class ClassifyResult:
    email_id: uuid.UUID
    success: bool
    action: str | None = None
    type: str | None = None
    confidence: str | None = None

@dataclass(frozen=True)
class RouteResult:
    email_id: uuid.UUID
    actions_dispatched: int
    actions_failed: int

@dataclass(frozen=True)
class CRMSyncTaskResult:
    email_id: uuid.UUID
    contact_id: str | None = None
    activity_id: str | None = None
    overall_success: bool = False

@dataclass(frozen=True)
class DraftTaskResult:
    email_id: uuid.UUID
    draft_id: uuid.UUID | None = None
    status: str = "pending"
```

**Naming note:** `CRMSyncTaskResult` and `DraftTaskResult` avoid collision with service-level `CRMSyncResult` and `DraftResult`.

## Scheduler pattern (from spec)

```python
# src/scheduler/main.py
async def main() -> None:
    settings = get_settings()
    # FAIL-FAST assertion (Cat 8 pre-mortem)
    assert settings.pipeline_scheduler_lock_ttl_seconds >= settings.polling_interval_seconds, (
        "Lock TTL must be >= poll interval"
    )
    scheduler = AsyncIOScheduler(timezone=utc)
    scheduler.add_job(
        poll_email_accounts_job,
        IntervalTrigger(seconds=settings.polling_interval_seconds),
    )
    scheduler.start()

# src/scheduler/jobs.py
async def poll_email_accounts_job() -> None:
    """For each active account: acquire Redis lock → enqueue ingest_task → release lock."""
    # Lock Redis per account_id prevents concurrent polls
    # Lock released in finally block (Cat 9: crash-safety via TTL expiry)
    # No imports from src/api/ — scheduler is a separate container
```

## Quality gates

```bash
# Types
mypy src/tasks/result_types.py src/tasks/celery_app.py src/tasks/pipeline.py src/scheduler/

# Lint
ruff check src/tasks/ src/scheduler/ && ruff format --check src/tasks/ src/scheduler/

# Tests
pytest tests/tasks/ tests/scheduler/ -v

# Full regression
pytest tests/ -q

# Grep checks
grep -rn "AsyncResult" src/tasks/                     # Must be EMPTY
grep -n "except Exception" src/tasks/pipeline.py      # Exactly 5 matches (one per task)
grep -rn "from src.api" src/scheduler/                # Must be EMPTY (scheduler ≠ API)
grep -n "300\|3600\|60\b" src/tasks/pipeline.py src/scheduler/jobs.py  # No hardcoded constants

# PII check
grep -rn "subject\|body_plain\|sender_email\|snippet" src/tasks/pipeline.py src/scheduler/jobs.py
# Only email_id and account_id in log statements
```

## Test patterns

### Pipeline chain test

```python
# Mock ALL 5 services, verify each task:
# 1. Loads email from DB
# 2. Calls service method
# 3. Commits state transition
# 4. Calls next_task.delay() on success
# Verify final state: DRAFT_GENERATED (full chain) or ROUTED (no CRM/draft)
```

### Partial failure test

```python
# For each stage N:
# 1. Mock stages 1..N-1 to succeed
# 2. Mock stage N to raise
# 3. Verify email stays in state of stage N-1
# 4. Verify stages N-1 data persists in DB
```

### Scheduler lock test

```python
# 1. Acquire lock → returns True
# 2. Second acquire → returns False (same key)
# 3. TTL expires → next acquire returns True
# 4. Crash simulation: no explicit release → lock expires by TTL
```

## Style rules

- snake_case files/vars/functions, PascalCase classes
- Type hints on public functions, no `dict[str, Any]`
- Contract docstrings on `run_pipeline()` and each task
- `structlog.get_logger(__name__)`
- Commit: `feat(pipeline): block-12 — celery pipeline + scheduler, N tests`
