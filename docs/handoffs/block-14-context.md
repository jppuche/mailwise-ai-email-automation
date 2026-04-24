# Block 14: Analytics & Admin Endpoints — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-14-api-config.md`.

## What to build

`src/api/routers/` — Four new routers (categories, integrations, analytics, logs) with Pydantic schemas, three new services (CategoryService, AnalyticsService, IntegrationService), and two new ORM models + Alembic migration (FewShotExample, SystemLog). Extends the B13 API layer with admin management and observability endpoints.

### Files to create

| File | Purpose |
|------|---------|
| `src/models/few_shot.py` | `FewShotExample` ORM model — admin-curated classification examples |
| `src/models/system_log.py` | `SystemLog` ORM model — structured audit log entries |
| `alembic/versions/xxx_add_few_shot_and_system_log.py` | Migration for new tables |
| `src/services/category_service.py` | `CategoryService` — CRUD + FK guard + reorder for categories |
| `src/services/analytics_service.py` | `AnalyticsService` — SQL aggregation queries + CSV streaming |
| `src/services/integration_service.py` | `IntegrationService` — adapter status + test_connection |
| `src/api/schemas/categories.py` | Category/FewShotExample/Feedback API schemas |
| `src/api/schemas/integrations.py` | Integration status/config/test schemas |
| `src/api/schemas/analytics.py` | Volume/distribution/accuracy/routing schemas |
| `src/api/schemas/logs.py` | LogEntry/LogFilter schemas |
| `src/api/routers/categories.py` | 12 endpoints: ActionCategory + TypeCategory CRUD, FewShotExample CRUD, Feedback list |
| `src/api/routers/integrations.py` | 8 endpoints: status + test for 4 adapter types |
| `src/api/routers/analytics.py` | 5 endpoints: volume, distribution, accuracy, routing, CSV export |
| `src/api/routers/logs.py` | 1 endpoint: paginated filtered log list |
| `tests/api/test_categories_router.py` | Category CRUD + FK guard + reorder + auth |
| `tests/api/test_integrations_router.py` | Status + test_connection + auth |
| `tests/api/test_analytics_router.py` | Aggregation queries + CSV streaming |
| `tests/api/test_logs_router.py` | Paginated logs + filters |

### Files to modify

| File | Change |
|------|--------|
| `src/api/main.py` | Register 4 new routers + new exception handlers |
| `src/core/config.py` | Add `analytics_max_date_range_days`, `analytics_csv_chunk_size`, `analytics_default_timezone` |
| `src/core/exceptions.py` | Add `CategoryInUseError` (→ 409 with `affected_email_count`) |
| `src/api/exception_handlers.py` | Add handler for `CategoryInUseError` |
| `src/models/__init__.py` | Export new models (if used) |

## CRITICAL: Spec vs. codebase deltas

These are discrepancies between the B14 spec and the actual codebase. **Follow the codebase, not the spec, when they conflict.**

| Spec says | Codebase reality | Action |
|-----------|-------------------|--------|
| `FewShotExample` model exists (Block 1) | **Does NOT exist** — no ORM model, no migration, no table | **Create** `src/models/few_shot.py` + Alembic migration |
| `SystemLog` model exists (Block 1) | **Does NOT exist** — logging is via structlog, no DB table | **Create** `src/models/system_log.py` + Alembic migration |
| `IntegrationConfig` model exists (Block 1) | **Does NOT exist** — all config is env vars in `Settings` | **Adapt**: read config from `Settings`, adapter status from `test_connection()`. No DB-stored config. |
| `PUT /api/integrations/*/` updates DB config | Config is env vars (not DB-persisted) | **Drop PUT endpoints** — config is read-only at runtime. Keep GET (read Settings) + POST /test |
| `FeedbackItem.reviewer_note: str` | `ClassificationFeedback` has no `reviewer_note` field — only FK IDs | **Drop `reviewer_note`** — feedback stores category corrections, not freeform notes |
| `FeedbackItem.original_action: str` (slug) | ORM has `original_action_id: UUID` (FK to categories) | **JOIN** with `ActionCategory`/`TypeCategory` to resolve slugs in the response |
| `Email.received_at` | Field is named `Email.date` | **Map `date` → `received_at`** in analytics schemas (same as B13) |
| Spec references `ClassificationFeedback.corrected_at` | This field exists, NOT `created_at` for the correction timestamp | **Use `corrected_at`** for feedback timeline |
| `ActionCategoryCreate.color_hex` | ORM `ActionCategory` has NO `color_hex` column | **Drop `color_hex`** from create/update schemas — or add column via migration |
| `category_service.py` uses `await db.commit()` | B13 pattern: session managed by `get_async_db` (auto-commit/rollback) | **Use `await db.flush()` + `await db.refresh()`** — let the DI session handle commit |
| `DeletedResponse(deleted=True)` | B13 pattern: DELETE returns 204 No Content (no body) | **Use 204** for consistency with B13 `routing_rules.py` and `drafts.py` |

## Existing API code — what's already built

### `src/api/main.py` (current — 5 routers, 7 exception handlers)

```python
app = FastAPI(title="mailwise", version="0.1.0", lifespan=lifespan)

# Exception handlers (7):
# AuthenticationError→401, AuthorizationError→403, NotFoundError→404,
# CategoryNotFoundError→404, InvalidStateTransitionError→409,
# DuplicateEmailError→409, DuplicateResourceError→409

# Routers:
# /api/v1/auth       (auth_router)
# /api/v1/emails     (emails_router)
# /api/v1/routing-rules (routing_rules_router)
# /api/v1/drafts     (drafts_router)
# /api/v1            (health_router → /health)
```

### `src/api/deps.py` (current — 5 DI functions)

```python
async def get_current_user(credentials, db) -> User:       # JWT validation, loads User
async def require_admin(current_user) -> User:              # Admin only (403 if not)
async def require_reviewer_or_admin(current_user) -> User:  # Admin or Reviewer (403 otherwise)
async def require_draft_access(draft_id, current_user, db) -> Draft:  # Load + auth check
async def get_routing_service() -> RoutingService:          # DI factory with deferred imports
```

### `src/core/exceptions.py` (current — 7 exceptions)

```python
class InvalidStateTransitionError(Exception): ...  # → 409
class CategoryNotFoundError(Exception): ...         # → 404
class DuplicateEmailError(Exception): ...           # → 409
class AuthenticationError(Exception): ...            # → 401
class AuthorizationError(Exception): ...             # → 403
class NotFoundError(Exception): ...                  # → 404
class DuplicateResourceError(Exception): ...         # → 409

# MUST ADD for B14:
class CategoryInUseError(Exception):                 # → 409 with affected_email_count
    def __init__(self, category_id: uuid.UUID, affected_email_count: int): ...
```

### `src/core/config.py` — Settings fields relevant to B14

```python
# Already exist:
llm_model_classify: str = "gpt-4o-mini"
llm_model_draft: str = "gpt-4o"
llm_temperature_classify: float = 0.1
llm_temperature_draft: float = 0.7
polling_interval_seconds: int = 300
classify_max_few_shot_examples: int = 10
openai_api_key: str = ""
anthropic_api_key: str = ""
slack_bot_token: str = ""
hubspot_access_token: str = ""
gmail_credentials_file: str = "secrets/gmail_credentials.json"
gmail_token_file: str = "secrets/gmail_token.json"
api_health_adapter_timeout_ms: int = 200
app_version: str = "0.1.0"

# MUST ADD for B14:
analytics_max_date_range_days: int = 365
analytics_csv_chunk_size: int = 1000
analytics_default_timezone: str = "UTC"
```

## ORM models — actual fields (from codebase)

### `ActionCategory` / `TypeCategory` (`src/models/category.py`)

```python
id: UUID                    # PK, default=uuid4
slug: String(100)           # UNIQUE, indexed
name: String(255)           # NOT NULL
description: Text           # NOT NULL, default=""
is_fallback: Boolean        # NOT NULL, default=False
is_active: Boolean          # NOT NULL, default=True
display_order: Integer      # NOT NULL, default=0
created_at, updated_at      # TimestampMixin (server_default=func.now())
# NOTE: NO color_hex column
```

### `ClassificationResult` (`src/models/classification.py`)

```python
id: UUID
email_id: UUID              # FK emails.id (CASCADE), indexed
action_category_id: UUID    # FK action_categories.id
type_category_id: UUID      # FK type_categories.id
confidence: Enum(ClassificationConfidence)  # "high" | "low"
raw_llm_output: JSONB
fallback_applied: Boolean   # default=False
classified_at: DateTime(tz) # server_default=func.now()
created_at, updated_at
```

### `ClassificationFeedback` (`src/models/feedback.py`)

```python
id: UUID
email_id: UUID              # FK emails.id (CASCADE), indexed
original_action_id: UUID    # FK action_categories.id (RESTRICT)
original_type_id: UUID      # FK type_categories.id (RESTRICT)
corrected_action_id: UUID   # FK action_categories.id (RESTRICT)
corrected_type_id: UUID     # FK type_categories.id (RESTRICT)
corrected_by: UUID          # FK users.id
corrected_at: DateTime(tz)  # server_default=func.now()
created_at, updated_at
# NOTE: NO reviewer_note field — feedback stores corrections, not freeform notes
```

### `Email` (`src/models/email.py`)

```python
id: UUID
provider_message_id: String(255)  # UNIQUE
thread_id: String(255) | None     # indexed
account: String(255)              # indexed
sender_email: String(255)
sender_name: String(255) | None
recipients: JSONB (list[RecipientData])
subject: Text                     # default=""
body_plain: Text | None           # PII — never in API list responses
body_html: Text | None
snippet: String(500) | None
date: DateTime(tz)                # ← THIS is received_at (column named "date")
attachments: JSONB
provider_labels: JSONB
state: Enum(EmailState)           # indexed, 12 values
processed_at: DateTime(tz) | None
created_at, updated_at

# Composite indexes: (state, date), (account, state)
```

### `RoutingAction` (`src/models/routing.py`)

```python
id: UUID
email_id: UUID              # FK emails.id (CASCADE), indexed
rule_id: UUID | None        # FK routing_rules.id (SET NULL)
channel: String(50)
destination: String(255)
priority: Integer
status: Enum(RoutingActionStatus)  # pending|dispatched|failed|skipped
dispatch_id: String(255) | None    # SHA-256[:32] idempotency key
dispatched_at: DateTime(tz) | None
attempts: Integer           # default=0
created_at, updated_at
```

### `CRMSyncRecord` (`src/models/crm_sync.py`)

```python
id: UUID
email_id: UUID              # FK emails.id (CASCADE), indexed
contact_id: String(255) | None
activity_id: String(255) | None
lead_id: String(255) | None
status: Enum(CRMSyncStatus)  # synced|failed|skipped
synced_at: DateTime(tz)      # server_default=func.now()
created_at, updated_at
```

## Models that DON'T exist — must create

### `FewShotExample` (to create: `src/models/few_shot.py`)

Spec schema (adapt from `docs/specs/block-14-api-config.md`):

```python
class FewShotExample(Base, TimestampMixin):
    __tablename__ = "few_shot_examples"

    id: Mapped[uuid.UUID]         # PK, default=uuid4
    email_snippet: Mapped[str]    # Text, NOT NULL — truncated example email
    action_slug: Mapped[str]      # String(100), NOT NULL — references ActionCategory.slug
    type_slug: Mapped[str]        # String(100), NOT NULL — references TypeCategory.slug
    rationale: Mapped[str | None] # Text, nullable — explanation for the LLM
    is_active: Mapped[bool]       # default=True
    created_at, updated_at        # TimestampMixin
```

Note: `action_slug` and `type_slug` are string references (not FK UUIDs) for flexibility — validated at service layer against active categories. This matches how `FeedbackExample` dataclass works in `src/services/schemas/classification.py`.

### `SystemLog` (to create: `src/models/system_log.py`)

```python
class SystemLog(Base, TimestampMixin):
    __tablename__ = "system_logs"

    id: Mapped[uuid.UUID]            # PK, default=uuid4
    timestamp: Mapped[datetime]      # DateTime(tz), NOT NULL, indexed
    level: Mapped[str]               # String(20), NOT NULL — "INFO"|"WARNING"|"ERROR"
    source: Mapped[str]              # String(100), NOT NULL — pipeline stage name
    message: Mapped[str]             # Text, NOT NULL
    email_id: Mapped[uuid.UUID | None]  # UUID, nullable — reference only (no FK)
    context: Mapped[dict[str, str]]  # JSONB, default={} — PII-safe: only IDs/slugs
    created_at, updated_at           # TimestampMixin
```

Note: `email_id` is NOT a FK — intentional. Logs should persist even if email is deleted. `context` is `dict[str, str]` (not `Any`) per PII policy.

## Adapter interfaces — test_connection() for integration router

All four adapters implement `test_connection()` with **NEVER RAISES** semantics:

### EmailAdapter (SYNC — not async)

```python
# src/adapters/email/base.py
def test_connection(self) -> ConnectionTestResult:
    # Returns: ConnectionTestResult(connected: bool, account: str | None,
    #          scopes: list[str], error: str | None)
    # SYNC method — must use asyncio.to_thread() in async context
```

### ChannelAdapter (async)

```python
# src/adapters/channel/base.py
async def test_connection(self) -> ConnectionTestResult:
    # Returns: ConnectionTestResult(success: bool, workspace_name: str | None,
    #          latency_ms: int, error_detail: str | None)
```

### CRMAdapter (async)

```python
# src/adapters/crm/base.py
async def test_connection(self) -> ConnectionTestResult:
    # Returns: ConnectionTestResult(success: bool, portal_id: str | None,
    #          latency_ms: int, error_detail: str | None)
```

### LLMAdapter (async)

```python
# src/adapters/llm/base.py
async def test_connection(self) -> ConnectionTestResult:
    # Returns: ConnectionTestResult(success: bool, model_used: str,
    #          latency_ms: int, error_detail: str | None)
    # NOTE: No connect() method — initialized with LLMConfig in constructor
```

**Critical for B14:**
- `test_connection()` NEVER raises — all errors captured in return value
- Integration router POST /test endpoints always return HTTP 200 (success=False is a valid result)
- EmailAdapter is SYNC — wrap with `asyncio.to_thread(adapter.test_connection)` (project pattern from B07/B12)

## Integration router — adapted design (no IntegrationConfig model)

Since `IntegrationConfig` doesn't exist and config lives in env vars (`Settings`), the integration router is **read-only for config** + **test_connection**:

```
GET    /api/v1/integrations/email           — read Gmail config from Settings (Admin)
POST   /api/v1/integrations/email/test      — test Gmail connection (Admin)

GET    /api/v1/integrations/channels        — read Slack config from Settings (Admin)
POST   /api/v1/integrations/channels/test   — test Slack connection (Admin)

GET    /api/v1/integrations/crm             — read HubSpot config from Settings (Admin)
POST   /api/v1/integrations/crm/test        — test HubSpot connection (Admin)

GET    /api/v1/integrations/llm             — read LLM config from Settings (Admin)
POST   /api/v1/integrations/llm/test        — test LLM connection (Admin)
```

**No PUT endpoints** — config changes require env var update + restart. GET endpoints read from `get_settings()` and mask sensitive values (show `api_key_configured: bool`, never the key itself).

## Category deletion guard — pre-mortem Cat 3

The spec mandates explicit count query before DELETE (never rely on `IntegrityError`):

```python
# In CategoryService:
async def delete_action_category(self, category_id: UUID, db: AsyncSession) -> None:
    # 1. Load category (NotFoundError if missing)
    # 2. Count ClassificationResults referencing this category
    affected = await db.scalar(
        select(func.count(ClassificationResult.id)).where(
            ClassificationResult.action_category_id == category_id
        )
    )
    # 3. If referenced → raise CategoryInUseError(category_id, affected)
    # 4. Also count ClassificationFeedback referencing this category
    #    (original_action_id OR corrected_action_id)
    # 5. If not referenced → db.delete(), flush
```

The `CategoryInUseError` handler returns 409 with `affected_email_count` in the body.

## Analytics service — GROUP BY, zero Python loops

```python
# CORRECT: Aggregation in SQL
stmt = select(
    func.date_trunc("day", Email.date).label("day"),
    func.count(Email.id).label("count"),
).where(
    Email.date >= filter.start_date,
    Email.date <= filter.end_date,
).group_by(text("day")).order_by(text("day"))

# INCORRECT: Never do this
emails = (await db.execute(select(Email))).scalars().all()
counts = {}
for email in emails:  # ← NEVER iterate all emails in Python
    day = email.date.date()
    counts[day] = counts.get(day, 0) + 1
```

### CSV export — streaming

```python
async def stream_csv(filter, db) -> AsyncGenerator[str, None]:
    yield "id,received_at,action,type,state\n"
    offset = 0
    while True:
        rows = await db.execute(query.offset(offset).limit(chunk_size))
        batch = rows.all()
        if not batch:
            break
        for row in batch:
            yield f"{row.id},{row.date.isoformat()},{action},{type},{row.state.value}\n"
        offset += chunk_size
```

Router uses `StreamingResponse(generator, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=..."})`.

## Endpoint structure (full list — 26 endpoints)

```
# Categories — ActionCategory (Admin for write, Reviewer+ for read)
GET    /api/v1/categories/actions              — list ordered by display_order
POST   /api/v1/categories/actions              — create (201)
GET    /api/v1/categories/actions/{id}         — get one
PUT    /api/v1/categories/actions/{id}         — update (partial)
DELETE /api/v1/categories/actions/{id}         — delete with FK guard (204 or 409)
PUT    /api/v1/categories/actions/reorder      — reorder display_order

# Categories — TypeCategory (same pattern)
GET    /api/v1/categories/types               — list
POST   /api/v1/categories/types               — create (201)
GET    /api/v1/categories/types/{id}          — get one
PUT    /api/v1/categories/types/{id}          — update
DELETE /api/v1/categories/types/{id}          — delete with FK guard
PUT    /api/v1/categories/types/reorder       — reorder

# FewShotExample (Admin only)
GET    /api/v1/classification/examples        — list
POST   /api/v1/classification/examples        — create (201)
PUT    /api/v1/classification/examples/{id}   — update
DELETE /api/v1/classification/examples/{id}   — delete (204)

# Feedback (Admin only, read-only)
GET    /api/v1/classification/feedback        — paginated list with resolved slugs

# Integrations (Admin only)
GET    /api/v1/integrations/email             — Gmail config (masked)
POST   /api/v1/integrations/email/test        — test Gmail connection
GET    /api/v1/integrations/channels          — Slack config (masked)
POST   /api/v1/integrations/channels/test     — test Slack connection
GET    /api/v1/integrations/crm               — HubSpot config (masked)
POST   /api/v1/integrations/crm/test          — test HubSpot connection
GET    /api/v1/integrations/llm               — LLM config (masked)
POST   /api/v1/integrations/llm/test          — test LLM connection

# Analytics (Reviewer+)
GET    /api/v1/analytics/volume               — email volume time series
GET    /api/v1/analytics/classification-distribution — action/type pie charts
GET    /api/v1/analytics/accuracy             — classification accuracy %
GET    /api/v1/analytics/routing              — routing channel stats
GET    /api/v1/analytics/export               — CSV streaming (Admin only)

# Logs (Admin only)
GET    /api/v1/logs                           — paginated, filtered
```

## Authorization matrix

```
Endpoint                                        Admin  Reviewer
────────────────────────────────────────────────────────────────
GET  /api/v1/categories/actions                 ✓      ✓
POST /api/v1/categories/actions                 ✓      ✗
PUT  /api/v1/categories/actions/{id}            ✓      ✗
DELETE /api/v1/categories/actions/{id}          ✓      ✗
PUT  /api/v1/categories/actions/reorder         ✓      ✗
(TypeCategory endpoints — same as ActionCategory)

GET  /api/v1/classification/examples            ✓      ✗
POST /api/v1/classification/examples            ✓      ✗
PUT  /api/v1/classification/examples/{id}       ✓      ✗
DELETE /api/v1/classification/examples/{id}     ✓      ✗

GET  /api/v1/classification/feedback            ✓      ✗

GET  /api/v1/integrations/*                     ✓      ✗
POST /api/v1/integrations/*/test                ✓      ✗

GET  /api/v1/analytics/volume                   ✓      ✓
GET  /api/v1/analytics/classification-dist.     ✓      ✓
GET  /api/v1/analytics/accuracy                 ✓      ✓
GET  /api/v1/analytics/routing                  ✓      ✓
GET  /api/v1/analytics/export                   ✓      ✗

GET  /api/v1/logs                               ✓      ✗
```

## Existing service schemas — what B14 reuses

### `FeedbackExample` (from `src/services/schemas/classification.py`)

```python
class FeedbackExample(BaseModel):
    """A few-shot example for the classification prompt.
    Constructed from ClassificationFeedback ORM + Email body snippet."""
    email_snippet: str
    correct_action: str   # slug
    correct_type: str     # slug
```

This is what the classification service uses for few-shot prompts. B14's `FewShotExample` model stores admin-curated versions of these.

## Architecture constraints (inherited from B13)

| Rule | Details |
|------|---------|
| Thin routers — zero try/except | Domain exceptions → `exception_handlers.py`. Services handle try/except for DB/adapter ops. |
| No `dict[str, Any]` in schemas | All fields typed. Exception: `LogEntry.context: dict[str, str]` (documented, PII-safe) |
| No direct adapter imports in routers | Adapters accessed via services + DI factories |
| Category DELETE: explicit count query | Never rely on `IntegrityError` — portable across SQLite/PostgreSQL |
| Analytics: GROUP BY in SQL | Zero Python loops for aggregation. `func.count()`, `func.date_trunc()` |
| CSV export: streaming generator | `AsyncGenerator` + `StreamingResponse` — never `.all()` then iterate |
| PII policy | No `body_plain` in responses, no credentials in integration status, `email_id` only in logs |
| `from_attributes` mode | `ConfigDict(from_attributes=True)` on schemas that map from ORM |

## Test patterns (same as B13)

### conftest.py fixtures (reuse from `tests/api/conftest.py`)

```python
# Already available:
mock_db          # AsyncMock session
admin_user       # MagicMock User(role=ADMIN)
reviewer_user    # MagicMock User(role=REVIEWER)
admin_client     # AsyncClient with admin auth + mock_db
reviewer_client  # AsyncClient with reviewer auth + mock_db
unauthenticated_client  # AsyncClient with mock_db, no auth
client           # AsyncClient with NO mock_db override (for path existence tests)
```

### Mock pattern for sequential DB queries

```python
mock_db.execute.side_effect = [
    _scalar_one_result(5),       # COUNT query
    _scalars_all_result([cat1, cat2]),  # paginated results
]
```

### Mock pattern for server_default timestamps

```python
async def _refresh_timestamps(obj: object) -> None:
    obj.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    obj.updated_at = datetime(2024, 1, 1, tzinfo=UTC)

mock_db.refresh.side_effect = _refresh_timestamps
```

## Quality gates

```bash
# 1. Types (ordered — schemas first, then services, then routers)
mypy src/api/schemas/categories.py src/api/schemas/integrations.py \
     src/api/schemas/analytics.py src/api/schemas/logs.py
mypy src/services/category_service.py src/services/analytics_service.py \
     src/services/integration_service.py
mypy src/api/routers/categories.py src/api/routers/integrations.py \
     src/api/routers/analytics.py src/api/routers/logs.py

# 2. Lint
ruff check src/api/ src/services/category_service.py \
     src/services/analytics_service.py src/services/integration_service.py
ruff format --check src/api/ src/services/

# 3. Tests (ordered)
pytest tests/api/test_categories_router.py -v
pytest tests/api/test_integrations_router.py -v
pytest tests/api/test_analytics_router.py -v
pytest tests/api/test_logs_router.py -v

# 4. Architecture checks
grep -rn "try:" src/api/routers/categories.py src/api/routers/integrations.py \
     src/api/routers/analytics.py src/api/routers/logs.py
# Expected: EMPTY (thin routers — no try/except)

grep -rn "dict\[str, Any\]\|: Any" src/api/schemas/categories.py \
     src/api/schemas/integrations.py src/api/schemas/analytics.py
# Expected: EMPTY

grep -rn "api_key\|token\|password\|secret" src/api/schemas/integrations.py
# Expected: only *_configured: bool fields

# 5. Full regression
pytest tests/ -q
```

## Style rules

- snake_case files/vars/functions, PascalCase classes
- Type hints on public functions, no `dict[str, Any]`
- Contract docstrings on router functions and service methods
- `structlog.get_logger(__name__)`
- `from __future__ import annotations` at top of every new file
- Commit: `feat(api): block-14 — analytics & admin endpoints, N tests`
