# Block 13: REST API Core — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-13-api-core.md`.

## What to build

`src/api/` — Thin REST routers (email CRUD, routing rules, drafts, health) with Pydantic schemas, FastAPI DI, and global exception handlers. Routers delegate to services (B7-B11) — no business logic in the API layer. OpenAPI auto-generated from types.

### Files to create

| File | Purpose |
|------|---------|
| `src/api/schemas/common.py` | `PaginatedResponse[T]`, `ErrorResponse`, `HealthResponse`, `AdapterHealthItem` |
| `src/api/schemas/emails.py` | `EmailListItem`, `EmailDetailResponse`, `EmailFilter`, `PaginationParams`, retry/reclassify/feedback schemas |
| `src/api/schemas/routing.py` | `RoutingRuleCreate`, `RoutingRuleUpdate`, `RoutingRuleResponse`, `RuleTestRequest/Response` |
| `src/api/schemas/drafts.py` | `DraftListItem`, `DraftDetailResponse`, approve/reject/reassign schemas |
| `src/api/routers/emails.py` | 4 endpoints: list (paginated+filtered), detail, retry, reclassify + 2 classification sub-endpoints |
| `src/api/routers/routing_rules.py` | 6 endpoints: CRUD + reorder + test |
| `src/api/routers/drafts.py` | 5 endpoints: list, detail, approve, reject, reassign |
| `src/api/routers/health.py` | 1 endpoint: aggregated health check with adapter probing |
| `src/api/exception_handlers.py` | Domain exception → HTTP status code mapping |
| `src/api/dependencies.py` | New: service DI factories (`get_classification_service`, `get_routing_service`, etc.) |
| `tests/api/test_emails_router.py` | List, detail, retry, reclassify, classification, feedback, auth enforcement |
| `tests/api/test_routing_rules_router.py` | CRUD, reorder, test, admin-only enforcement |
| `tests/api/test_drafts_router.py` | List, detail, approve, reject, reassign, reviewer access scoping |
| `tests/api/test_health_router.py` | All adapters up, degraded, always HTTP 200 |
| `tests/api/test_auth_router.py` | Login, refresh, logout, me (may already exist in tests/auth/) |
| `tests/api/test_pagination.py` | Edge cases: page_size=0, page_size>100, offset > total |

### Files to modify

| File | Change |
|------|--------|
| `src/api/main.py` | Add new routers, new exception handlers, versioned prefixes, proper health endpoint |
| `src/api/deps.py` | Add service DI factories (rename to `dependencies.py` per spec, or keep `deps.py` — existing code imports `deps.py`) |
| `src/core/exceptions.py` | Add `NotFoundError`, `DuplicateResourceError` |
| `src/core/config.py` | Add `app_version`, `api_health_adapter_timeout_ms` if Cat 8 needed |

## CRITICAL: Spec vs. codebase deltas

These are discrepancies between the B13 spec and the actual codebase. **Follow the codebase, not the spec, when they conflict.**

| Spec says | Codebase reality | Action |
|-----------|-------------------|--------|
| `LoginRequest(email, password)` | `LoginRequest(username, password)` — already implemented in B2 | **Keep `username`** — do not change |
| `settings.cors_allowed_origins` | Field is `settings.cors_origins` | **Use `cors_origins`** |
| `settings.app_version` | Does not exist | **Add to `Settings`** or hardcode `"0.1.0"` |
| `PermissionDeniedError` | `AuthorizationError` already exists and is mapped to 403 | **Keep `AuthorizationError`** for auth-related; add `PermissionDeniedError` only if needed for non-auth 403s |
| `NotFoundError` | Does not exist in `src/core/exceptions.py` | **Add it** |
| `DuplicateResourceError` | Does not exist | **Add it** |
| `RoutingRule.description` field | ORM model has NO `description` column | **Drop from API schemas** OR add Alembic migration (recommended: drop, avoid migration in API block) |
| `Draft.model_used`, `Draft.fallback_applied` | ORM model has NO such columns | **Drop from `DraftSummary`** — these exist in service-level `DraftResult` only, not persisted |
| `ClassificationSummary.is_fallback` | `ClassificationResult` ORM has `fallback_applied: bool` | **Map `fallback_applied` → `is_fallback`** in the response (rename for API clarity) |
| Auth router prefix `/auth` | Currently mounted as `app.include_router(auth_router)` with router-level `prefix="/auth"` | **Change to `app.include_router(auth_router, prefix="/api/v1")` or update router prefix** |
| `require_draft_access` dependency | Does not exist | **Create in `deps.py`** |

## Existing API code — what's already built

### `src/api/main.py` (current)

```python
app = FastAPI(title="mailwise", version="0.1.0", lifespan=lifespan)

# CORS: settings.cors_origins (NOT cors_allowed_origins)
# Exception handlers: AuthenticationError→401, AuthorizationError→403
# Routers: ONLY auth_router (prefix="/auth")
# Health: GET /health → {"status": "ok"} (stub, no adapter checks)
# Lifespan: yield, then close_redis() on shutdown
```

### `src/api/deps.py` (current)

```python
async def get_current_user(credentials, db) -> User:
    # Validates JWT, loads User from DB
    # Raises AuthenticationError (→ 401)

async def require_admin(current_user) -> User:
    # Raises AuthorizationError (→ 403) if not Admin

async def require_reviewer_or_admin(current_user) -> User:
    # Raises AuthorizationError if neither role
```

Uses `get_async_db` from `src/core/database.py`:
```python
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    # Yields session, commits on success, rolls back on exception
```

### `src/api/schemas/auth.py` (current — DO NOT recreate)

```python
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)

class TokenResponse(BaseModel):
    access_token: str; refresh_token: str; token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)

class UserResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: uuid.UUID; username: str; role: UserRole; is_active: bool
```

### `src/api/routers/auth.py` (current — DO NOT recreate)

```python
router = APIRouter(prefix="/auth", tags=["auth"])
# POST /auth/login → TokenResponse
# POST /auth/refresh → TokenResponse
# POST /auth/logout → 204
# GET /auth/me → UserResponse
```

## Implementation gaps — services that DON'T exist

B13 needs operations that current services don't provide. These must be implemented directly:

### 1. No routing rule CRUD in `RoutingService`

`RoutingService` only has `route()` and `test_route()`. Full CRUD (list, create, get, update, delete, reorder) must be implemented via direct DB queries in the router or a new thin service. Recommended: direct DB queries in router (thin layer, simple CRUD).

### 2. No draft workflow in `DraftGenerationService`

`DraftGenerationService` only has `generate()`. Approve/reject/reassign are pure ORM operations:
- **approve**: set `draft.status = APPROVED`, `draft.reviewed_at = now()`, optionally call `email_adapter.create_draft()` for Gmail push
- **reject**: set `draft.status = REJECTED`, `draft.reviewed_at = now()`
- **reassign**: set `draft.reviewer_id = new_reviewer_id`

### 3. No retry/reclassify service methods

Retry and reclassify must call Celery tasks directly:
```python
from src.tasks.pipeline import run_pipeline, classify_task

# Retry (from failed state):
run_pipeline(email_id)  # enqueues classify_task

# Reclassify (reset classification, re-enqueue):
email.transition_to(EmailState.SANITIZED)  # requires valid transition
classify_task.delay(str(email_id))
```

### 4. No classification read or feedback submission

- `GET /emails/{id}/classification` → query `ClassificationResult` ORM directly
- `POST /emails/{id}/classification/feedback` → insert into `ClassificationFeedback` ORM directly

## ORM models — actual fields (from codebase)

### `Email` fields

```python
id: uuid.UUID                         # PK
provider_message_id: str              # unique
thread_id: str | None                 # index
account: str                          # index
sender_email: str
sender_name: str | None
recipients: list[RecipientData]       # JSONB
subject: str                          # Text
body_plain: str | None                # Text
body_html: str | None                 # Text
snippet: str | None                   # String(500)
date: datetime                        # timezone=True
attachments: list[AttachmentData]     # JSONB
provider_labels: list[str]            # JSONB
state: EmailState                     # Enum, index
processed_at: datetime | None
created_at, updated_at                # from TimestampMixin
```

### `EmailState` enum — all values

```python
# Happy path:
FETCHED → SANITIZED → CLASSIFIED → ROUTED → CRM_SYNCED → DRAFT_GENERATED → COMPLETED → RESPONDED

# Error states:
CLASSIFICATION_FAILED, ROUTING_FAILED, CRM_SYNC_FAILED, DRAFT_FAILED

# Recovery transitions:
CLASSIFICATION_FAILED → SANITIZED
ROUTING_FAILED → CLASSIFIED
CRM_SYNC_FAILED → ROUTED
DRAFT_FAILED → CRM_SYNCED
```

### `ClassificationResult` fields

```python
id, email_id, action_category_id, type_category_id,
confidence (ClassificationConfidence: "high"|"low"),
raw_llm_output (JSONB), fallback_applied (bool),
classified_at, created_at, updated_at
```

### `RoutingRule` fields

```python
id, name (String 255), priority (int, index), is_active (bool),
conditions (list[RoutingConditions] JSONB), actions (list[RoutingActions] JSONB),
created_at, updated_at
# NOTE: NO description field — spec has it, ORM does not
```

### `RoutingAction` fields

```python
id, email_id, rule_id (nullable FK), channel, destination,
priority, status (RoutingActionStatus), dispatch_id, dispatched_at,
attempts, created_at, updated_at
```

### `Draft` fields

```python
id, email_id, content (Text), status (DraftStatus: pending|approved|rejected),
reviewer_id (nullable FK → users), reviewed_at (nullable),
pushed_to_provider (bool), created_at, updated_at
# NOTE: NO model_used, NO fallback_applied — those are in DraftResult service schema only
```

### `CRMSyncRecord` fields

```python
id, email_id, contact_id, activity_id, lead_id,
status (CRMSyncStatus: synced|failed|skipped), synced_at,
created_at, updated_at
```

### `ClassificationFeedback` fields

```python
id, email_id, original_action_id, original_type_id,
corrected_action_id, corrected_type_id, corrected_by (FK → users),
corrected_at, created_at, updated_at
```

### `ActionCategory` / `TypeCategory` fields

```python
id, slug, name, description, is_fallback, is_active, display_order,
created_at, updated_at
```

## Service schemas — what the API maps FROM

### `ClassificationServiceResult` (from `src/services/schemas/classification.py`)

```python
class ClassificationServiceResult(BaseModel):
    email_id: uuid.UUID
    action_slug: str
    type_slug: str
    confidence: Literal["high", "low"]
    fallback_applied: bool
    heuristic_disagreement: bool
    heuristic_result: HeuristicResult | None
    db_record_id: uuid.UUID
```

### `RoutingResult` (from `src/services/schemas/routing.py`)

```python
class RoutingResult(BaseModel):
    email_id: uuid.UUID; rules_matched: int; rules_executed: int
    actions_dispatched: int; actions_failed: int
    was_routed: bool; routing_action_ids: list[uuid.UUID]; final_state: str
```

### `RoutingContext` (input for `test_route`)

```python
class RoutingContext(BaseModel):
    email_id: uuid.UUID; action_slug: str; type_slug: str
    confidence: Literal["high", "low"]
    sender_email: str; sender_domain: str; subject: str; snippet: str
    sender_name: str | None = None
```

### `RuleTestResult` (from `src/services/schemas/routing.py`)

```python
class RuleTestResult(BaseModel):
    context: RoutingContext
    rules_matched: list[RuleMatchResult]
    would_dispatch: list[RoutingActionDef]
    total_actions: int; dry_run: bool = True
```

### `DraftResult` (from `src/services/schemas/draft.py`)

```python
class DraftResult(BaseModel):
    email_id: uuid.UUID; draft_id: uuid.UUID | None; gmail_draft_id: str | None
    status: str; model_used: str | None; fallback_applied: bool
    error_detail: str | None
```

## Pipeline integration (from Block 12)

```python
# src/tasks/pipeline.py
from src.tasks.pipeline import run_pipeline, classify_task

# Retry: re-enqueue from failed state
run_pipeline(email_id)  # plain function, calls classify_task.delay()

# Reclassify: reset to SANITIZED then re-enqueue
# Must transition email state first, then enqueue
classify_task.delay(str(email_id))
```

## Core exceptions — what exists vs what to add

```python
# EXISTING in src/core/exceptions.py:
class InvalidStateTransitionError(Exception): ...  # → 409
class CategoryNotFoundError(Exception): ...
class DuplicateEmailError(Exception): ...
class AuthenticationError(Exception): ...            # → 401 (already mapped)
class AuthorizationError(Exception): ...             # → 403 (already mapped)

# MUST ADD for B13:
class NotFoundError(Exception): ...                  # → 404
class DuplicateResourceError(Exception): ...         # → 409
```

## Authorization matrix

```
Endpoint                              Admin  Reviewer
─────────────────────────────────────────────────────
GET  /api/v1/emails                   ✓      ✓
GET  /api/v1/emails/{id}              ✓      ✓
POST /api/v1/emails/{id}/retry        ✓      ✗
POST /api/v1/emails/{id}/reclassify   ✓      ✗
GET  /api/v1/emails/{id}/classification ✓    ✓
POST /api/v1/emails/{id}/classification/feedback ✓ ✓
GET  /api/v1/routing-rules            ✓      ✗
POST /api/v1/routing-rules            ✓      ✗
GET  /api/v1/routing-rules/{id}       ✓      ✗
PUT  /api/v1/routing-rules/{id}       ✓      ✗
DELETE /api/v1/routing-rules/{id}     ✓      ✗
PUT  /api/v1/routing-rules/reorder    ✓      ✗
POST /api/v1/routing-rules/test       ✓      ✗
GET  /api/v1/drafts                   ✓      ✓ (own only)
GET  /api/v1/drafts/{id}              ✓      ✓ (own only)
POST /api/v1/drafts/{id}/approve      ✓      ✓ (own only)
POST /api/v1/drafts/{id}/reject       ✓      ✓ (own only)
POST /api/v1/drafts/{id}/reassign     ✓      ✗
GET  /api/v1/health                   public (no auth)
POST /api/v1/auth/login               public (no auth)
POST /api/v1/auth/refresh             public (no auth)
POST /api/v1/auth/logout              ✓      ✓
GET  /api/v1/auth/me                  ✓      ✓
```

## Architecture constraints

| Rule | Details |
|------|---------|
| Thin routers — zero try/except | Domain exceptions → `exception_handlers.py`. Only `health.py._check_adapter` has try/except |
| No `dict[str, Any]` in schemas | All fields typed. `response_model` explicit on every data endpoint |
| No direct adapter imports in routers | All via services/dependencies |
| Health always HTTP 200 | "degraded" if any adapter fails, but never 503 |
| Health adapter check: `asyncio.gather` with 200ms timeout | Parallel, return_exceptions=True |
| PII policy | `body_plain` never in list responses. Only `snippet` exposed. `email_id` only in logs |
| `from_attributes` mode | Use `model_config = {"from_attributes": True}` on schemas that map directly from ORM |

## Quality gates

```bash
# Types (ordered — schemas first, then infra, then routers, then main)
mypy src/api/schemas/
mypy src/api/dependencies.py src/api/exception_handlers.py
mypy src/api/routers/
mypy src/api/main.py

# Lint
ruff check src/api/ && ruff format --check src/api/

# Tests (ordered — auth first, pagination, then data endpoints)
pytest tests/api/test_auth_router.py -v
pytest tests/api/test_pagination.py -v
pytest tests/api/test_emails_router.py -v
pytest tests/api/test_routing_rules_router.py -v
pytest tests/api/test_drafts_router.py -v
pytest tests/api/test_health_router.py -v

# Full regression
pytest tests/ -q

# Grep checks
grep -n "try:" src/api/routers/emails.py src/api/routers/routing_rules.py \
    src/api/routers/drafts.py src/api/routers/auth.py
# Expected: EMPTY (thin routers)

grep -rn "dict\[str, Any\]\|: Any" src/api/schemas/
# Expected: EMPTY

grep -n "response_model=None" src/api/routers/
# Expected: EMPTY

grep -rn "from src.adapters" src/api/routers/
# Expected: EMPTY (routers don't import adapters directly)
```

## Test patterns

### Router tests with httpx AsyncClient

```python
from httpx import ASGITransport, AsyncClient
from src.api.main import app

@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

# Override DI dependencies for test isolation:
app.dependency_overrides[get_async_db] = lambda: mock_db
app.dependency_overrides[get_current_user] = lambda: mock_admin_user
```

### Auth enforcement test pattern

```python
# No token → 401
response = await client.get("/api/v1/emails")
assert response.status_code == 401

# Reviewer can't access admin endpoint → 403
app.dependency_overrides[get_current_user] = lambda: reviewer_user
response = await client.post("/api/v1/emails/{id}/retry", json={})
assert response.status_code == 403
```

## Style rules

- snake_case files/vars/functions, PascalCase classes
- Type hints on public functions, no `dict[str, Any]`
- Contract docstrings on each router function
- `structlog.get_logger(__name__)`
- Commit: `feat(api): block-13 — REST API core, N tests`
