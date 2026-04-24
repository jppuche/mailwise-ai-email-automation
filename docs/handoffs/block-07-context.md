# Block 07: Ingestion Service — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-07-ingestion.md`.

## What to build

`src/services/` — IngestionService that orchestrates email fetch → dedup → sanitize → store (FETCHED → SANITIZED). Per-email isolation, distributed lock, thread awareness.

### Files to create

| File | Purpose |
|------|---------|
| `src/services/schemas/ingestion.py` | IngestionResult (frozen dataclass), IngestionBatchResult, SkipReason/FailureReason enums |
| `src/services/schemas/__init__.py` | Package init |
| `src/services/ingestion.py` | IngestionService class (ingest_batch + helpers) |
| `src/tasks/ingestion_task.py` | Celery task wrapper |

### Files to modify

| File | Change |
|------|--------|
| `src/core/config.py` | Add `ingestion_lock_ttl_seconds`, `ingestion_lock_key_prefix` |

**Note:** `ingestion_batch_size` (50) and `polling_interval_seconds` (300) already exist in config.

## Architecture overview

```
APScheduler (scheduler container)
  → celery.send_task("tasks.ingest_emails", args=[account_id])
    → Celery worker executes ingest_emails_task
      → IngestionService.ingest_batch(account_id)
        1. Acquire Redis lock (SET NX EX)
        2. Fetch emails from EmailAdapter
        3. For each email:
           a. Dedup check (DB query by provider_message_id)
           b. Thread awareness (is this the newest in thread?)
           c. Sanitize body (local computation)
           d. Store in DB → state=FETCHED → commit
           e. Transition to SANITIZED → commit
        4. Release lock
        5. Return IngestionBatchResult
```

## Critical decisions (from SCRATCHPAD + spec)

- `IngestionResult` is `@dataclass(frozen=True)` — immutable after creation
- `IngestionBatchResult` is `@dataclass` (NOT frozen — built incrementally)
- Redis lock key per account_id: `f"{prefix}:{account_id}"`
- Two independent commits per email: FETCHED then SANITIZED (Cat 6, D13)
- Thread awareness: newest message per `thread_id` gets `classify_next=True`
- Snippet truncated by calling service, not adapter (consistent with B06 CRM pattern)

## Open questions (from SCRATCHPAD — resolve during implementation)

- `asyncio.Lock` vs `Redis SET NX EX` for poll lock → **RESOLVED: Redis** (multi-worker)
- `@dataclass(frozen=True)` for `IngestionResult` → Yes (spec confirms)

## Email model fields needed (from `src/models/email.py`)

```python
class Email(Base, TimestampMixin):
    id: UUID (primary key, auto-generated)
    provider_message_id: str (unique — dedup key)
    thread_id: str | None (indexed — thread grouping)
    account: str (indexed — email account identifier)
    sender_email: str
    sender_name: str | None
    recipients: list[RecipientData] (JSONB)
    subject: str
    body_plain: str | None
    body_html: str | None
    snippet: str | None (max 500 chars)
    date: datetime (timezone-aware)
    attachments: list[AttachmentData] (JSONB)
    provider_labels: list[str] (JSONB)
    state: EmailState (enum, default FETCHED)
    processed_at: datetime | None
```

**State transitions for B07:**
- New email → `state=FETCHED` (default on insert) → `transition_to(SANITIZED)` → commit
- `transition_to()` enforces `VALID_TRANSITIONS` — raises `InvalidStateTransitionError` if invalid (bug, NOT caught)

## EmailMessage adapter schema → Email ORM mapping

The `IngestionService` must map `EmailMessage` (adapter boundary) to `Email` (ORM model):

```python
# EmailMessage (from adapter)          → Email (ORM model)
msg.gmail_message_id                   → email.provider_message_id
msg.thread_id                          → email.thread_id
msg.from_address                       → email.sender_email
# (no sender_name in adapter schema)   → email.sender_name = None or extract from headers
msg.to_addresses + msg.cc_addresses    → email.recipients (need to add "type" field)
msg.subject                            → email.subject
msg.body_plain                         → sanitize → email.body_plain
msg.body_html                          → email.body_html
msg.snippet                            → sanitize → email.snippet
msg.received_at                        → email.date
msg.attachments                        → email.attachments (add attachment_id)
msg.provider_labels                    → email.provider_labels
```

**RecipientData conversion:**
- Adapter `RecipientData`: `{email: str, name: str | None}` (no `type` field)
- ORM `RecipientData`: `{email: str, name: str, type: str}` (has `type`: "to"/"cc"/"bcc")
- Map `to_addresses` with `type="to"`, `cc_addresses` with `type="cc"`

## Sanitizer usage

```python
from src.core.sanitizer import sanitize_email_body, SanitizedText

# Local computation — NO try/except (D8)
sanitized_body = sanitize_email_body(
    msg.body_plain or "",
    max_length=settings.max_body_length,  # default 4000
)
# For snippet:
sanitized_snippet = sanitize_email_body(
    msg.snippet or "",
    max_length=settings.snippet_length,  # default 200
    strip_html=True,
)
```

`sanitize_email_body` NEVER raises. Returns `SanitizedText("")` on invalid input.

## Exception strategy (try-except D7/D8)

### External-state operations (try/except with specific types)

| Boundary | Exception type | Scope |
|----------|---------------|-------|
| EmailAdapter.fetch_new_messages | `EmailAdapterError` | Whole batch fails |
| DB dedup query | `SQLAlchemyError` | Per-email isolation |
| DB write (store email) | `SQLAlchemyError` | Per-email isolation |
| DB write (transition) | `SQLAlchemyError` | Per-email isolation |
| Redis lock acquire/release | `RedisError` | Whole batch fails |

### Local computation (NO try/except — D8)

| Operation | Why no try/except |
|-----------|-------------------|
| `sanitize_email_body()` | Pure function, never raises |
| `email.transition_to()` | Bug if fails → `InvalidStateTransitionError` → NOT caught |
| EmailMessage → Email mapping | Conditionals only |
| IngestionResult construction | Dataclass, no external state |

### Celery top-level handler (only permitted bare except)

```python
except Exception as exc:  # noqa: BLE001 — top-level Celery handler (D7 exception)
    logger.error("ingestion_task_failed", account_id=account_id, error=str(exc))
    raise self.retry(exc=exc)
```

## Redis lock pattern

```python
async def _acquire_poll_lock(self, account_id: str) -> bool:
    """SET NX EX — atomic Redis operation."""
    lock_key = f"{settings.ingestion_lock_key_prefix}:{account_id}"
    acquired = await self._redis.set(lock_key, "1", nx=True, ex=settings.ingestion_lock_ttl_seconds)
    return acquired is not None

async def _release_poll_lock(self, account_id: str) -> None:
    lock_key = f"{settings.ingestion_lock_key_prefix}:{account_id}"
    await self._redis.delete(lock_key)
```

**Important:** Use `try/finally` to ensure lock release even on exceptions:
```python
if not await self._acquire_poll_lock(account_id):
    return IngestionBatchResult(... empty ...)
try:
    # ... process batch ...
finally:
    await self._release_poll_lock(account_id)
```

## Thread awareness

```python
# thread_id extraction (local — no try/except)
thread_id = msg.thread_id  # str | None from adapter

if thread_id is not None:
    # DB query (external-state — try/except)
    existing_in_thread = await session.execute(
        select(Email)
        .where(Email.thread_id == thread_id)
        .order_by(Email.date.desc())
        .limit(1)
    )
    newest = existing_in_thread.scalar_one_or_none()
    if newest is not None and msg.received_at <= newest.date:
        # Not the newest — skip for classification
        results.append(IngestionResult(..., skip_reason=THREAD_NOT_NEWEST))
        continue
```

## Existing code you need to know

### Dual session factories — `src/core/database.py`

```python
# Async (FastAPI) — for IngestionService
AsyncSessionLocal: async_sessionmaker[AsyncSession]
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:

# Sync (Celery) — for ingestion_task
SyncSessionLocal: sessionmaker[Session]
def get_sync_db() -> Generator[Session, None, None]:
```

**Celery task pattern:** sync session + `get_sync_db()` context manager.
**Service pattern:** async session injected via constructor.

### Redis client — `src/adapters/redis_client.py`

Currently token-focused. The lock functions (`_acquire_poll_lock`, `_release_poll_lock`) can live inside `IngestionService` directly (they use the injected Redis client, not the module-level singleton).

### Email adapter — `src/adapters/email/base.py`

```python
class EmailAdapter(abc.ABC):
    @abc.abstractmethod
    async def fetch_new_messages(
        self, *, since: datetime, limit: int
    ) -> list[EmailMessage]:
```

### Exceptions already defined — `src/core/exceptions.py`

```python
class InvalidStateTransitionError(Exception): ...  # Bug, NOT caught
class DuplicateEmailError(Exception): ...           # Available for dedup
```

## Load-bearing defaults (Cat 8)

| Default | Value | Env Var | Already in config? |
|---------|-------|---------|--------------------|
| Batch size | `50` | `INGESTION_BATCH_SIZE` | Yes |
| Poll interval | `300`s | `POLLING_INTERVAL_SECONDS` | Yes |
| Lock TTL | `300`s | `INGESTION_LOCK_TTL_SECONDS` | **No — add** |
| Lock key prefix | `"mailwise:ingest:lock"` | `INGESTION_LOCK_KEY_PREFIX` | **No — add** |
| Max body length | `4000` | `MAX_BODY_LENGTH` | Yes |
| Snippet length | `200` | `SNIPPET_LENGTH` | Yes |

## Privacy (Sec 11.4 — MANDATORY)

- Logger NEVER logs `subject`, `body_plain`, `from_address`, `snippet`
- OK to log: `account_id`, `email_id` (UUID), `provider_message_id`, `thread_id`
- Use `logger.info("ingestion_email_stored", email_id=str(email.id), provider_message_id=msg.gmail_message_id)`

## Test patterns

### Test file locations (flat convention)

```
tests/unit/test_ingestion_schemas.py   # dataclass validation
tests/unit/test_ingestion_service.py   # service with mocked adapter + DB
tests/unit/test_ingestion_task.py      # Celery task with mocked service
```

**Note:** Spec says `tests/services/` but project convention is flat `tests/unit/`. Follow convention.

### IngestionService mocking

```python
@pytest.fixture
def mock_email_adapter() -> MagicMock:
    adapter = AsyncMock(spec=EmailAdapter)
    adapter.fetch_new_messages.return_value = [_make_email_message()]
    return adapter

@pytest.fixture
def mock_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.set.return_value = True  # lock acquired
    redis.delete.return_value = None
    return redis

@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    session.commit = AsyncMock()
    return session
```

### Key test scenarios

1. **Happy path**: 3 emails → 3 ingested, state=SANITIZED
2. **Dedup**: same `provider_message_id` twice → second is DUPLICATE
3. **Thread skip**: older thread message → THREAD_NOT_NEWEST
4. **Per-email isolation**: email 2 DB error → email 1 and 3 still ingested
5. **Lock contention**: lock already held → empty batch result returned
6. **Adapter failure**: `EmailAdapterError` → whole batch fails, lock released
7. **Empty batch**: adapter returns [] → IngestionBatchResult with 0 counts
8. **Two commits per email**: FETCHED commit + SANITIZED commit verified separately

## Celery task pattern

```python
# The task is SYNC (Celery worker), but IngestionService is ASYNC
# Option A: asyncio.run() inside task (simplest for Phase N)
# Option B: sync service + sync DB session

# Spec suggests Option A with run_async():
def ingest_emails_task(self, account_id: str) -> None:
    with get_sync_db() as session:
        service = IngestionService(...)
        result = asyncio.run(service.ingest_batch(account_id))
```

**Warning:** `asyncio.run()` creates a new event loop. If the service uses async DB sessions, you need async session in async context OR redesign service to be sync. The spec uses `run_async()` — this needs to be a helper or `asyncio.run()`.

**Simpler approach (since no Celery infra yet):** Make `IngestionService` fully async and test it directly. The Celery task wrapper can be a thin shell that calls `asyncio.run()`. Block 12 (Celery pipeline) will formalize the sync/async bridge.

## Quality gates (must pass before commit)

```bash
python -m mypy src/services/ src/tasks/
python -m ruff check src/services/ src/tasks/
python -m ruff format src/services/ src/tasks/ --check
pytest tests/unit/test_ingestion_schemas.py -v
pytest tests/unit/test_ingestion_service.py -v
pytest tests/unit/test_ingestion_task.py -v
pytest tests/ -q  # full non-integration suite
bash scripts/validate-docs.sh
```

## Style rules

- snake_case files/vars/functions, PascalCase classes
- Type hints on public functions, no `dict[str, Any]` at boundaries
- Contract docstrings: Preconditions, Guarantees, Errors raised, Errors silenced
- `# noqa: BLE001` on Celery top-level bare except
- `structlog.get_logger(__name__)` — no `# type: ignore` needed
- Commit: `feat(ingestion): block-07 — ingestion service, N tests`
