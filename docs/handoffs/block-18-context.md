# Block 18: E2E Test Suite — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-18-tests.md`.

## What to build

E2E tests for the full pipeline (FETCHED → COMPLETED), cross-block integration tests
(API + pipeline), partial failure tests (one per task), draft workflow tests, config
change propagation tests, and coverage gap-fill to reach >70%. This block is
**backend-only** — no frontend work. Factories with factory-boy, mock adapters that
implement real ABCs (mypy-verified), Celery eager mode.

## What already exists (your starting point)

**Test infrastructure (DO NOT recreate):**
- `pyproject.toml`: `asyncio_mode = "auto"`, `testpaths = ["tests"]`
- Root `conftest.py`: env vars for DATABASE_URL, REDIS_URL, JWT_SECRET_KEY
- `tests/conftest.py`: `--run-integration` flag, `integration` marker, skip logic
- `tests/integration/conftest.py`: real DB fixtures (module-scoped), NullPool, Alembic upgrade, `async_client`, `admin_tokens`
- `tests/api/conftest.py`: mocked DB + auth dependency overrides
- `tests/models/conftest.py`: sync engine, db_session, migrated_db, alembic_runner
- 1616+ backend tests (unit + API + integration + task + contract + core)
- 342 frontend tests (separate, Vitest — not relevant to B18)

**Test directories that exist:**
```
tests/
  conftest.py              # markers, --run-integration
  models/                  # model + migration tests
  unit/                    # 30+ unit test files (all services/adapters)
  integration/             # auth integration tests (real DB + Redis)
  api/                     # API router tests (mocked DB)
  tasks/                   # pipeline chain + partial failure unit tests
  scheduler/               # scheduler lock + poll job tests
  contract/                # adapter contract tests (4 files)
  core/                    # config + sanitizer tests
```

**NOT created yet (B18 must create):**
- `tests/factories.py` — factory-boy model factories
- `tests/e2e/` — E2E test directory with conftest and test files
- `tests/coverage/` — gap-fill tests after coverage analysis

## CRITICAL: Spec vs. codebase deltas

The B18 spec has 21 amendments. **Follow the codebase, not the original spec text.**

| # | Spec says | Codebase reality | Action |
|---|-----------|-------------------|--------|
| X1 | `Email.received_at` | `Email.date` | Use `date` in factories/tests |
| X2 | `Email.from_address` | `Email.sender_email` | Use `sender_email` |
| X3 | `Draft.body` | `Draft.content` | Use `content` |
| X4 | `User.email` | `User.username` | Use `username` |
| X6 | `EmailAccount` model exists | Does NOT exist — `Email.account` is `str` | No account FK |
| X7 | `PipelineRunRecord` model | Does NOT exist | Assert via Email state + child records |
| 6 | `ClassificationResult.confidence: float` | `ClassificationConfidence` enum: `"high"` / `"low"` | Use enum values |
| 7 | `*_category_id: int` | All FK columns are `uuid.UUID` | Use UUID |
| 8 | `RoutingAction.generate_draft: bool` | Does NOT exist on model — in `RoutingRule.actions` JSONB | Remove from factory |
| 9 | `RoutingAction.crm_sync: bool` | Same — not on model | Remove from factory |
| 10 | `Draft.body` | `Draft.content` | Rename in factory |
| 11 | `UserFactory.email` | `User.username` | Rename in factory |
| 12 | `AuthService.hash_password()` | Use `bcrypt.hashpw()` directly (passlib incompatible) | Direct bcrypt |
| 14 | `CRMSyncResult` | Actual: `CRMSyncTaskResult` (`src/tasks/result_types.py:46`) | Use actual name |
| 15 | `DraftResult` | Actual: `DraftTaskResult` (`src/tasks/result_types.py:59`) | Use actual name |
| 16 | `from src.tasks import ingest_task` | `src/tasks/__init__.py` is empty | Import from individual modules |
| 17 | `MockGmailAdapter.test_connection() -> bool` | Returns `ConnectionTestResult` dataclass | Match real return type |
| 18 | `MockLLMAdapter.classify()` is sync | Actual is `async def` | Use `async def` |
| 19 | `ingest_task(str(email.id))` direct call | Use `task.run()` for testing (bypasses dispatch) | `task.run()` |
| 20 | `DRAFT_REJECTED` email state | No such EmailState — `DraftStatus.REJECTED` on Draft | Email stays `DRAFT_GENERATED` |
| 21 | Mock adapters as simple classes | Real adapters use `_ensure_connected()` | Set `_connected = True` |

## ORM Models — exact field names

### Email (`src/models/email.py`)

```python
class Email(Base, TimestampMixin):
    id: uuid.UUID
    provider_message_id: str        # NOT gmail_message_id
    thread_id: str | None
    account: str                     # plain str, NOT uuid FK
    sender_email: str                # NOT from_address
    sender_name: str | None
    recipients: list[RecipientData]  # JSONB
    subject: str
    body_plain: str | None
    body_html: str | None
    snippet: str | None
    date: datetime                   # NOT received_at
    attachments: list[AttachmentData]  # JSONB
    provider_labels: list[str]       # JSONB
    state: EmailState                # StrEnum, uppercase values
    processed_at: datetime | None
```

### EmailState — full state machine

```
FETCHED → SANITIZED → CLASSIFIED → ROUTED → CRM_SYNCED → DRAFT_GENERATED → COMPLETED → RESPONDED
              |              |           |              |
    CLASSIFICATION_FAILED  ROUTING_FAILED  CRM_SYNC_FAILED  DRAFT_FAILED
```

Values are uppercase strings (`EmailState.FETCHED == "FETCHED"`).

### ClassificationResult (`src/models/classification.py`)

```python
class ClassificationResult(Base, TimestampMixin):
    id: uuid.UUID
    email_id: uuid.UUID              # FK → emails.id
    action_category_id: uuid.UUID    # FK → action_categories.id (UUID, not int)
    type_category_id: uuid.UUID      # FK → type_categories.id (UUID, not int)
    confidence: ClassificationConfidence  # enum: "high" | "low" (lowercase)
    raw_llm_output: dict             # JSONB
    fallback_applied: bool
    classified_at: datetime
```

### RoutingRule (`src/models/routing.py`)

```python
class RoutingRule(Base, TimestampMixin):
    id: uuid.UUID
    name: str
    priority: int
    is_active: bool
    conditions: list[RoutingConditions]  # JSONB array of TypedDict
    actions: list[RoutingActions]        # JSONB array of TypedDict — NOT separate rows
```

`RoutingActions` TypedDict: `{"channel": str, "destination": str, "template_id": str | None}`.
No `generate_draft` or `crm_sync` fields exist anywhere.

### RoutingAction (`src/models/routing.py`) — dispatched action record

```python
class RoutingAction(Base, TimestampMixin):
    id: uuid.UUID
    email_id: uuid.UUID
    rule_id: uuid.UUID | None        # FK, SET NULL on delete
    channel: str
    destination: str
    priority: int
    status: RoutingActionStatus      # "pending" | "dispatched" | "failed" | "skipped"
    dispatch_id: str | None          # SHA-256[:32] idempotency key
    dispatched_at: datetime | None
    attempts: int
```

### Draft (`src/models/draft.py`)

```python
class Draft(Base, TimestampMixin):
    id: uuid.UUID
    email_id: uuid.UUID
    content: str                     # NOT body
    status: DraftStatus              # "pending" | "approved" | "rejected" (lowercase)
    reviewer_id: uuid.UUID | None
    reviewed_at: datetime | None
    pushed_to_provider: bool
```

### User (`src/models/user.py`)

```python
class User(Base, TimestampMixin):
    id: uuid.UUID
    username: str                    # NOT email
    password_hash: str               # bcrypt.hashpw() directly, NOT passlib
    role: UserRole                   # "admin" | "reviewer" (lowercase)
    is_active: bool
```

### ActionCategory / TypeCategory (`src/models/category.py`)

```python
class ActionCategory(Base, TimestampMixin):
    id: uuid.UUID; slug: str; name: str; description: str
    is_fallback: bool; is_active: bool; display_order: int

class TypeCategory(Base, TimestampMixin):
    id: uuid.UUID; slug: str; name: str; description: str
    is_fallback: bool; is_active: bool; display_order: int
```

### CRMSyncRecord (`src/models/crm_sync.py`)

```python
class CRMSyncRecord(Base, TimestampMixin):
    id: uuid.UUID; email_id: uuid.UUID
    contact_id: str | None; activity_id: str | None; lead_id: str | None
    status: CRMSyncStatus           # "synced" | "failed" | "skipped"
    synced_at: datetime
```

## Adapter ABCs — exact signatures for mock compliance

### EmailAdapter (`src/adapters/email/base.py`)

```python
class EmailAdapter(abc.ABC):
    def connect(self, credentials: EmailCredentials) -> ConnectionStatus: ...
    def fetch_new_messages(self, since: datetime, limit: int) -> list[EmailMessage]: ...
    def mark_as_processed(self, message_id: str) -> None: ...
    def create_draft(self, to: str, subject: str, body: str,
                     in_reply_to: str | None = None) -> DraftId: ...
    def get_labels(self) -> list[Label]: ...
    def apply_label(self, message_id: str, label_id: str) -> None: ...
    def test_connection(self) -> ConnectionTestResult: ...  # NOT -> bool
```

### LLMAdapter (`src/adapters/llm/base.py`)

```python
class LLMAdapter(abc.ABC):
    async def classify(self, prompt: str, system_prompt: str,
                       options: ClassifyOptions) -> ClassificationResult: ...  # ASYNC
    async def generate_draft(self, prompt: str, system_prompt: str,
                             options: DraftOptions) -> DraftText: ...           # ASYNC
    async def test_connection(self) -> ConnectionTestResult: ...
```

### ChannelAdapter (`src/adapters/channel/base.py`)

```python
class ChannelAdapter(abc.ABC):
    async def connect(self, credentials: ChannelCredentials) -> ConnectionStatus: ...
    async def send_notification(self, payload: RoutingPayload,
                                destination_id: str) -> DeliveryResult: ...
    async def test_connection(self) -> ConnectionTestResult: ...
    async def get_available_destinations(self) -> list[Destination]: ...
```

### CRMAdapter (`src/adapters/crm/base.py`)

```python
class CRMAdapter(abc.ABC):
    async def connect(self, credentials: CRMCredentials) -> ConnectionStatus: ...
    async def lookup_contact(self, email: str) -> Contact | None: ...
    async def create_contact(self, data: CreateContactData) -> Contact: ...
    async def log_activity(self, contact_id: str, activity: ActivityData) -> ActivityId: ...
    async def create_lead(self, data: CreateLeadData) -> LeadId: ...
    async def update_field(self, contact_id: str, field: str, value: str) -> None: ...
    async def test_connection(self) -> ConnectionTestResult: ...
```

## Celery task structure

### Pipeline tasks (`src/tasks/pipeline.py`)

```
ingest_task(account_id: str, since_iso: str)  @celery_app.task(bind=True)
  → per email: classify_task.delay(email_id_str)
    → route_task.delay(email_id_str)
      → pipeline_crm_sync_task.delay(email_id_str)  [if was_routed]
        → pipeline_draft_task.delay(email_id_str)    [if state == CRM_SYNCED]
```

- All tasks use `@celery_app.task(bind=True)` with `asyncio.run()` bridging to async `_run_*` helpers
- For testing: use `task.run()` (bypasses dispatch, already bound — per CLAUDE.md learned pattern)
- `run_pipeline(email_id: UUID)` is a plain function (NOT a Celery task) — calls `classify_task.delay(str(email_id))`

### Result types (`src/tasks/result_types.py`)

```python
@dataclass(frozen=True)
class IngestResult:
    account_id: str; emails_fetched: int; emails_skipped: int; emails_failed: int

@dataclass(frozen=True)
class ClassifyResult:
    email_id: uuid.UUID; success: bool
    action: str | None = None; type: str | None = None; confidence: str | None = None

@dataclass(frozen=True)
class RouteResult:
    email_id: uuid.UUID; actions_dispatched: int; actions_failed: int

@dataclass(frozen=True)
class CRMSyncTaskResult:  # NOT CRMSyncResult
    email_id: uuid.UUID; contact_id: str | None = None
    activity_id: str | None = None; overall_success: bool = False

@dataclass(frozen=True)
class DraftTaskResult:    # NOT DraftResult
    email_id: uuid.UUID; draft_id: uuid.UUID | None = None; status: str = "pending"
```

**No `PipelineRunRecord` ORM model exists.** Verify pipeline results via Email state transitions + child records (ClassificationResult, RoutingAction, CRMSyncRecord, Draft).

## Celery eager mode setup

```python
# tests/e2e/conftest.py
from src.tasks.celery_app import celery_app

@pytest.fixture(autouse=True, scope="module")
def celery_eager_mode():
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True  # Propagate exceptions
    yield
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False
```

## DB isolation for E2E

E2E tests with Celery eager mode require real commits (each task creates its own `AsyncSessionLocal()` and commits independently — D13 design). Transaction rollback (`begin_nested()`) CANNOT wrap these.

**Recommended approach** (matches existing `tests/integration/conftest.py` pattern):
- Module-scoped DB setup with Alembic migrations
- UUID-suffixed identifiers per test run to avoid collisions
- `NullPool` mandatory for async engine
- Module-scoped `migrated_db` fixture (upgrade-only, no teardown downgrade)
- Function-scoped `reset_redis_singleton` (autouse) to reset `_redis_client = None`

## Existing test patterns to follow

### Task testing pattern (`tests/tasks/test_pipeline_chain.py`)

1. `task.run()` not `task()` — bypasses dispatch, already bound
2. Deferred imports patched via `sys.modules` injection (tasks use `from src.X import Y` inside body)
3. `AsyncSessionLocal` context manager mocked as `AsyncMock` with `__aenter__`/`__aexit__`
4. Coroutine cleanup: `inspect.iscoroutine(coro); coro.close()` to suppress ResourceWarning

### Integration test pattern (`tests/integration/conftest.py`)

```python
# Module-scoped migration fixture
@pytest.fixture(scope="module")
async def migrated_db_module():
    cfg = _get_alembic_config()
    command.upgrade(cfg, "head")
    yield

# Module-scoped async engine
@pytest.fixture(scope="module")
async def override_db(migrated_db_module):
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    # ... override app.dependency_overrides[get_async_db]

# Module-scoped httpx client
@pytest.fixture(scope="module")
async def async_client(override_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

# Function-scoped Redis reset (autouse, sync — avoids event loop mismatch)
@pytest.fixture(autouse=True)
def reset_redis_singleton():
    import src.adapters.redis_client as rc
    rc._redis_client = None
```

### Password hashing in tests

```python
import bcrypt
password_hash = bcrypt.hashpw(b"test_password", bcrypt.gensalt()).decode()
```

NOT `passlib` — incompatible with bcrypt>=4.2 on Python 3.14.

## Files to create

| File | Purpose |
|------|---------|
| `tests/factories.py` | factory-boy factories for all domain models (corrected field names) |
| `tests/e2e/__init__.py` | Package marker |
| `tests/e2e/conftest.py` | Celery eager mode, mock adapter stubs (ABC-compliant), E2E DB fixtures |
| `tests/e2e/test_pipeline_e2e.py` | Happy path: FETCHED → ... → COMPLETED; verify state + child records |
| `tests/e2e/test_pipeline_partial_failure.py` | 5 scenarios: one failure per task; verify N-1 committed, N not |
| `tests/e2e/test_api_pipeline_integration.py` | POST /emails/{id}/retry → pipeline runs → state changes in DB |
| `tests/e2e/test_draft_workflow.py` | Approve (push to provider), reject (DraftStatus.REJECTED), reassign |
| `tests/e2e/test_config_changes.py` | Category/rule changes via API affect next pipeline run |
| `tests/coverage/` | Gap-fill tests generated after coverage analysis |

## Files to modify

| File | Change |
|------|--------|
| `tests/conftest.py` | Add `--run-e2e` flag and `e2e` marker (or reuse `integration`) |
| `pyproject.toml` | Add `--cov-fail-under=70` to pytest addopts (optional — can pass on CLI) |

## Alignment chart quality rules (mandatory exit criteria)

1. **Every API test MUST verify response body** — not just status code
2. **Every exception test MUST specify exact type** — `pytest.raises(SpecificError)`, never `Exception`
3. **Every state transition test MUST verify before AND after state**
4. **Every adapter mock MUST verify call args** — `assert_called_once_with(...)`, not just `assert_called()`
5. **Prohibited**: `assert True`, `assert result is not None` as sole assertion
6. **E2E tests MUST verify DB state** — not just HTTP responses

## Quality gates (ordered)

```bash
# 1. Type safety
mypy tests/factories.py tests/e2e/conftest.py

# 2. Lint
ruff check tests/ && ruff format --check tests/

# 3. E2E happy path
pytest tests/e2e/test_pipeline_e2e.py -v --run-e2e

# 4. Partial failures
pytest tests/e2e/test_pipeline_partial_failure.py -v --run-e2e

# 5. Cross-block integration
pytest tests/e2e/test_api_pipeline_integration.py -v --run-e2e

# 6. Draft workflow
pytest tests/e2e/test_draft_workflow.py -v --run-e2e

# 7. Config changes
pytest tests/e2e/test_config_changes.py -v --run-e2e

# 8. Coverage analysis
pytest --cov=src --cov-report=term-missing -q

# 9. Gap-fill tests
# Write tests/coverage/test_gap_*.py for modules below 70%

# 10. Coverage gate
pytest --cov=src --cov-fail-under=70

# 11. Evil test audit
grep -rn "raises(Exception)" tests/          # MUST be empty
grep -rn "assert True$" tests/               # MUST be empty
grep -rn "\.assert_called()" tests/e2e/      # MUST be empty (use assert_called_once_with)
```

## Pre-implementation decisions needed

### 1. E2E marker strategy

Two options:
- **Option A**: New `--run-e2e` flag + `e2e` marker (cleanest separation)
- **Option B**: Reuse existing `--run-integration` flag (simpler, E2E is a subset of integration)
- **Recommended**: Option A — E2E tests have different infrastructure requirements (Celery eager + full DB)

### 2. DB isolation approach

E2E tests need real commits (Celery eager tasks open their own sessions). Options:
- **Option A**: UUID-suffixed identifiers per test + manual cleanup (matches existing integration pattern)
- **Option B**: Schema-per-test-class with CREATE/DROP SCHEMA (strongest, slowest)
- **Recommended**: Option A — proven pattern in `tests/integration/conftest.py`

### 3. Coverage gap-fill scope

After running `pytest --cov=src --cov-report=term-missing`:
- Priority 1: Error paths in services (LLM/CRM/Slack connection errors)
- Priority 2: Alternative config (different models, retry counts)
- Priority 3: Edge cases (empty body, non-ASCII encoding, max attachments)
- Priority 4: API pagination edge cases (empty page, out of range)

### 4. Docker requirement

E2E tests require PostgreSQL + Redis running. Options:
- Docker Desktop running + `docker compose up db redis` (current integration test approach)
- `--run-e2e` flag skips by default so `pytest` works without Docker
