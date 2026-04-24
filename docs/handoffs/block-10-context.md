# Block 10: CRM Sync Service — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-10-crm-sync.md`.

## What to build

`src/services/` — CRMSyncService that orchestrates: idempotency check via DB → contact lookup → conditional contact creation → activity logging → conditional lead creation → field updates → record CRMSyncRecord with partial state. Each CRM operation has its own try/except — no single try wrapping the entire chain.

### Files to create

| File | Purpose |
|------|---------|
| `src/services/schemas/crm_sync.py` | CRMSyncRequest, CRMSyncResult, CRMOperationStatus, CRMSyncConfig |
| `src/services/crm_sync.py` | CRMSyncService class (sync method + per-operation helpers) |
| `src/tasks/crm_sync_task.py` | Celery task: loads email, builds request, calls service, manages retry |
| `tests/unit/test_crm_sync_schemas.py` | Schema validation tests |
| `tests/unit/test_crm_sync_service.py` | Service tests (all operations, partial failure, idempotency) |
| `tests/unit/test_crm_sync_task.py` | Celery task retry/no-retry behavior |

### Files to modify

| File | Change |
|------|--------|
| `src/core/config.py` | Add `crm_sync_retry_max`, `crm_sync_backoff_base_seconds` (other CRM settings already exist) |

## Architecture overview

```
CRMSyncService.sync(request: CRMSyncRequest, db: AsyncSession) -> CRMSyncResult
  1. Idempotency check: load existing CRMSyncRecord for email_id
     - If status=SYNCED → return existing result (skip all CRM calls)
     - If status=FAILED → retry proceeds
     - If not found → fresh sync
  2. Contact lookup via CRM adapter
  3. If contact not found AND auto_create_contacts=True → create contact
  4. If contact_id exists → log activity
  5. If create_lead=True AND contact_id exists → create lead
  6. For each field_update → resolve CRM field name → update via adapter
  7. Record CRMSyncRecord with partial state (independent commit — D13)
  8. Return CRMSyncResult

Celery task wraps this:
  - CRMAuthError → NO retry (credentials invalid until renewed)
  - CRMRateLimitError → retry with backoff
  - Other exceptions → retry with default backoff
  - State transition: ROUTED → CRM_SYNCED or CRM_SYNC_FAILED
```

## CRITICAL: Spec vs actual code discrepancies

The spec's pseudocode uses **made-up names and signatures** that don't match the actual CRM adapter ABC. Use these corrections:

| Spec says | Actual code (use this) |
|-----------|----------------------|
| `ContactLookupResult` | `Contact \| None` (from `src.adapters.crm.schemas`) |
| `ContactRecord` | `Contact` |
| `ActivityRecord` → `.activity_id` | `ActivityId` (NewType of `str`) |
| `LeadRecord` → `.lead_id` | `LeadId` (NewType of `str`) |
| `create_contact(email=..., name=...)` | `create_contact(data: CreateContactData)` |
| `log_activity(contact_id=..., subject=..., snippet=..., ...)` | `log_activity(contact_id: str, activity: ActivityData)` |
| `create_lead(contact_id=..., subject=..., ...)` | `create_lead(data: CreateLeadData)` |
| `update_contact_field(contact_id, field, value)` | `update_field(contact_id: str, field: str, value: str)` |

## CRM Adapter ABC — actual method signatures (from `src/adapters/crm/base.py`)

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

**Key details:**
- `lookup_contact` returns `Contact | None` — None if not found (not an error)
- `create_contact` returns the full `Contact` (with `.id` = HubSpot ID as str)
- `log_activity` returns `ActivityId` (NewType of str), NOT an object with `.activity_id`
- `create_lead` returns `LeadId` (NewType of str), NOT an object with `.lead_id`
- `update_field` returns `None` — silences `FieldNotFoundError` per Sec 6.4

## CRM Adapter schemas (from `src/adapters/crm/schemas.py`)

```python
ActivityId = NewType("ActivityId", str)
LeadId = NewType("LeadId", str)

class Contact(BaseModel):
    id: str                          # Numeric HubSpot ID as str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

class CreateContactData(BaseModel):
    email: str                       # must contain '@' (field_validator)
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    source: str | None = None
    first_interaction_at: datetime | None = None

class ActivityData(BaseModel):
    subject: str
    timestamp: datetime              # timezone-aware
    classification_action: str
    classification_type: str
    snippet: str                     # pre-truncated by calling service
    email_id: str
    dashboard_link: str | None = None

class CreateLeadData(BaseModel):
    contact_id: str
    summary: str
    source: str
    lead_status: str = "NEW"
```

## CRM Adapter exceptions (from `src/adapters/crm/exceptions.py`)

```python
class CRMAdapterError(Exception):            # base — has original_error attribute
class CRMAuthError(CRMAdapterError):          # token invalid/revoked (HTTP 401)
class CRMRateLimitError(CRMAdapterError):     # HTTP 429 — has retry_after_seconds
class CRMConnectionError(CRMAdapterError):    # network/timeout/5xx
class DuplicateContactError(CRMAdapterError): # email already exists (HTTP 409)
class ContactNotFoundError(CRMAdapterError):  # contact_id not found (HTTP 404)
class FieldNotFoundError(CRMAdapterError):    # property doesn't exist in HubSpot
```

**Constructor patterns:**
```python
CRMAuthError("message", original_error=exc)
CRMRateLimitError("message", retry_after_seconds=30, original_error=exc)
CRMConnectionError("message", original_error=exc)
DuplicateContactError("message", original_error=exc)
```

## DB Models needed (B01 — what B10 reads/writes)

### CRMSyncRecord (write — one per sync attempt)

```python
# src/models/crm_sync.py
class CRMSyncStatus(StrEnum):
    SYNCED = "synced"
    FAILED = "failed"
    SKIPPED = "skipped"

class CRMSyncRecord(Base, TimestampMixin):
    __tablename__ = "crm_sync_records"
    id: Mapped[uuid.UUID]                # primary key, default=uuid.uuid4
    email_id: Mapped[uuid.UUID]          # FK → emails.id CASCADE, indexed
    contact_id: Mapped[str | None]       # String(255), nullable
    activity_id: Mapped[str | None]      # String(255), nullable
    lead_id: Mapped[str | None]          # String(255), nullable
    status: Mapped[CRMSyncStatus]        # Enum, not nullable
    synced_at: Mapped[datetime]          # DateTime(tz=True), server_default=now()
```

### Email (state transition)

```python
# State transitions for B10:
# Precondition: email.state == ROUTED (or CRM_SYNC_FAILED for retry)
# Happy path: ROUTED → CRM_SYNCED
# Error path: ROUTED → CRM_SYNC_FAILED
# Recovery: CRM_SYNC_FAILED → ROUTED (back to precondition for retry)

# ALWAYS use transition_to() — never direct assignment:
email.transition_to(EmailState.CRM_SYNCED)     # validated
email.state = EmailState.CRM_SYNCED             # WRONG — bypasses VALID_TRANSITIONS
```

## Exception strategy (try-except D7/D8)

### Per-operation try/except (the central pattern)

Each CRM operation gets its **own** try/except block. There is NO single try wrapping the entire chain.

```
Operation 1: contact lookup   → try/except → CRMAuthError: raise, CRMRateLimitError: raise, CRMAdapterError: record + continue
Operation 2: contact create   → try/except → same pattern (only if lookup returned None AND auto_create)
Operation 3: activity log     → try/except → same pattern (only if contact_id exists)
Operation 4: lead create      → try/except → same pattern (only if create_lead=True AND contact_id exists)
Operation 5: field updates    → try/except per field → same pattern (only if contact_id exists)
```

**CRMAuthError and CRMRateLimitError are ALWAYS re-raised** — they go to the Celery task for retry/no-retry decisions. CRMAdapterError (the generic base) is caught and recorded per-operation.

### Classification table

| Operation | Type | Pattern |
|-----------|------|---------|
| CRM API call (lookup, create, log, lead, update) | External state | try/except with CRMAuthError, CRMRateLimitError, CRMAdapterError |
| Idempotency check (DB query) | External state | try/except for SQLAlchemyError |
| Field mapping resolution | Local computation | Conditional (`if crm_field is None`) — D8 |
| Snippet truncation | Local computation | Slicing, no try/except — D8 |
| CRMSyncRecord write | External state | try/except for SQLAlchemyError |

## Config settings — what exists vs what to add

### Already in `config.py` (reuse these — do NOT add duplicates)

```python
hubspot_access_token: str = Field(default="")
hubspot_activity_snippet_length: int = Field(default=200)  # → CRMSyncConfig.activity_snippet_length
hubspot_auto_create_contacts: bool = Field(default=False)  # → CRMSyncConfig.auto_create_contacts
hubspot_default_lead_status: str = Field(default="NEW")
hubspot_api_timeout_seconds: int = Field(default=15)
```

### To ADD to `config.py` (after the Routing section)

```python
# CRM Sync (Cat 8: configurable defaults)
crm_sync_retry_max: int = Field(default=3)
crm_sync_backoff_base_seconds: int = Field(default=60)
```

**Map Settings → CRMSyncConfig:**
```python
CRMSyncConfig(
    auto_create_contacts=settings.hubspot_auto_create_contacts,
    activity_snippet_length=settings.hubspot_activity_snippet_length,
    retry_max=settings.crm_sync_retry_max,
    backoff_base_seconds=settings.crm_sync_backoff_base_seconds,
)
```

## Service schemas (from spec — spec schemas are accurate)

```python
# src/services/schemas/crm_sync.py

class CRMSyncConfig(BaseModel):
    auto_create_contacts: bool      # from hubspot_auto_create_contacts
    activity_snippet_length: int    # from hubspot_activity_snippet_length
    retry_max: int                  # from crm_sync_retry_max
    backoff_base_seconds: int       # from crm_sync_backoff_base_seconds

class CRMSyncRequest(BaseModel):
    email_id: uuid.UUID
    sender_email: str
    sender_name: str | None = None
    subject: str
    snippet: str                          # pre-truncated to activity_snippet_length
    classification_action: str            # ActionCategory slug
    classification_type: str              # TypeCategory slug
    received_at: datetime
    create_lead: bool = False
    field_updates: dict[str, str] = {}    # documented exception to no-dict rule

class CRMOperationStatus(BaseModel):
    operation: Literal["contact_lookup", "contact_create", "activity_log", "lead_create", "field_update"]
    success: bool
    crm_id: str | None = None
    skipped: bool = False
    error: str | None = None

class CRMSyncResult(BaseModel):
    email_id: uuid.UUID
    contact_id: str | None = None
    activity_id: str | None = None
    lead_id: str | None = None
    operations: list[CRMOperationStatus]
    overall_success: bool
    paused_for_auth: bool = False
```

**Note:** `field_updates: dict[str, str]` is a documented exception to D1 no-dict rule — both key and value are `str`, not `Any`.

## Constructor pattern (keyword-only, following B08/B09)

```python
class CRMSyncService:
    def __init__(
        self,
        *,
        crm_adapter: CRMAdapter,
        config: CRMSyncConfig,
    ) -> None:
        self._crm_adapter = crm_adapter
        self._config = config
```

**Do NOT inject `db`** — it's passed per-call to `sync()`, matching B08/B09 pattern.

## Corrected operation implementations (matching actual ABC)

### Operation 1: Contact lookup

```python
# ABC: async def lookup_contact(self, email: str) -> Contact | None
contact = await self._crm_adapter.lookup_contact(request.sender_email)
contact_id = contact.id if contact is not None else None
```

### Operation 2: Contact create (conditional)

```python
# ABC: async def create_contact(self, data: CreateContactData) -> Contact
created = await self._crm_adapter.create_contact(
    CreateContactData(
        email=request.sender_email,
        first_name=request.sender_name,  # sender_name maps to first_name
        source="mailwise",
        first_interaction_at=request.received_at,
    )
)
contact_id = created.id
```

**Handle DuplicateContactError:** If contact was created between lookup and create (race condition), catch `DuplicateContactError` and treat as success — do another lookup or use the contact_id from the error context.

### Operation 3: Activity log

```python
# ABC: async def log_activity(self, contact_id: str, activity: ActivityData) -> ActivityId
activity_id = await self._crm_adapter.log_activity(
    contact_id,
    ActivityData(
        subject=request.subject,
        timestamp=request.received_at,
        classification_action=request.classification_action,
        classification_type=request.classification_type,
        snippet=request.snippet[:self._config.activity_snippet_length],
        email_id=str(request.email_id),
    ),
)
# activity_id is a str (ActivityId NewType) — use directly
```

### Operation 4: Lead create (conditional)

```python
# ABC: async def create_lead(self, data: CreateLeadData) -> LeadId
lead_id = await self._crm_adapter.create_lead(
    CreateLeadData(
        contact_id=contact_id,
        summary=request.subject,
        source="mailwise",
    )
)
# lead_id is a str (LeadId NewType) — use directly
```

### Operation 5: Field updates

```python
# ABC: async def update_field(self, contact_id: str, field: str, value: str) -> None
# Returns None — the `-> None` pattern: bare `await`, never `result = await ...`
await self._crm_adapter.update_field(contact_id, field_name, field_value)
```

## Idempotency pattern

```python
# Query DB — NOT the CRM API
existing = await db.execute(
    select(CRMSyncRecord)
    .where(CRMSyncRecord.email_id == email_id)
    .order_by(CRMSyncRecord.synced_at.desc())
    .limit(1)
)
record = existing.scalar_one_or_none()
if record is not None and record.status == CRMSyncStatus.SYNCED:
    return self._build_result_from_record(record, email_id)
```

## Celery task pattern

```python
@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def crm_sync_task(self, email_id: str) -> None:
    """Top-level Celery task — only place where except Exception is allowed."""
    # Uses SyncSessionLocal — Celery tasks run sync
    # BUT CRM adapter is async → need asyncio.run() or event loop wrapper
    # See async/sync boundary note below
```

**Async/sync boundary:** The CRMAdapter ABC is fully async (all methods use `async def`). Celery tasks run synchronously. The task must bridge this gap — likely with `asyncio.run()` wrapping the async service call.

**Retry behavior:**
- `CRMAuthError` → **NO retry** (log, set CRM_SYNC_FAILED, return without raising)
- `CRMRateLimitError` → `self.retry(exc=exc, countdown=exc.retry_after_seconds or default_delay)`
- `Exception` → `self.retry(exc=exc)` (top-level handler — only allowed bare except)

## Privacy (MANDATORY — Sec 6.5)

- `CRMSyncRequest` has NO `body_plain` or `body_html` field — impossible by construction
- `snippet` pre-truncated to `activity_snippet_length` before CRM call
- Logger NEVER logs `subject`, `body_plain`, `sender_email`, `snippet`
- OK to log: `email_id`, `contact_id`, `activity_id`, `lead_id`, `operation`, `status`

## Partial failure semantics (Cat 6 — D13)

- Contact created + activity log failed → `CRMSyncRecord.contact_id` populated, `activity_id=None`. Status: FAILED.
- On retry: idempotency detects contact exists (via lookup), skips creation, retries activity log.
- Each CRM operation is independent — failure in one does NOT cancel subsequent operations (UNLESS contact_id is needed and was never obtained).
- `CRMSyncRecord` committed independently — persists even if email state transition fails after.

## Test patterns

### Test file locations (flat convention from B03-B09)

```
tests/unit/test_crm_sync_schemas.py
tests/unit/test_crm_sync_service.py
tests/unit/test_crm_sync_task.py
```

**NOTE:** Spec says `tests/services/` — IGNORE this. Use `tests/unit/` (flat convention established in B03).

### Key test scenarios

**CRMSyncService:**
1. Happy path: all 5 operations succeed → CRMSyncResult.overall_success=True
2. Contact lookup returns None + auto_create=False → skip create, no activity/lead (no contact_id)
3. Contact lookup returns None + auto_create=True → create contact → proceed
4. Contact lookup succeeds + activity log fails → contact_id populated, activity_id=None
5. CRMAuthError on any operation → re-raised (not caught by service)
6. CRMRateLimitError on any operation → re-raised
7. CRMAdapterError on activity log → recorded, lead create still attempts
8. Idempotency: existing SYNCED record → return cached, 0 CRM calls
9. Idempotency: existing FAILED record → retry proceeds
10. DuplicateContactError on create → handle gracefully
11. Field mapping: unknown field → log warning, skip, continue
12. Field update: FieldNotFoundError silenced by adapter (transparent to service)
13. Snippet truncated to activity_snippet_length

**Celery task:**
1. CRMAuthError → NO retry, state=CRM_SYNC_FAILED
2. CRMRateLimitError → retry with backoff
3. Generic exception → retry with default backoff
4. Email not found → log error, return (no retry)
5. State transition: success → CRM_SYNCED, failure → CRM_SYNC_FAILED
6. Max retries exhausted → CRM_SYNC_FAILED

### Mocking pattern

```python
# Mock CRM adapter (all async methods)
mock_adapter = AsyncMock(spec=CRMAdapter)
mock_adapter.lookup_contact.return_value = Contact(
    id="12345", email="test@example.com"
)
mock_adapter.log_activity.return_value = ActivityId("67890")
mock_adapter.create_lead.return_value = LeadId("11111")

# Inject via constructor
service = CRMSyncService(
    crm_adapter=mock_adapter,
    config=CRMSyncConfig(
        auto_create_contacts=False,
        activity_snippet_length=200,
        retry_max=3,
        backoff_base_seconds=60,
    ),
)

# Mock DB (same pattern as B08/B09)
mock_db = AsyncMock(spec=AsyncSession)
mock_db.execute.side_effect = [...]  # sequential mock returns
```

## Existing code patterns to follow (from B07-B09)

- Constructor injection: `__init__(*, adapter, config)` keyword-only
- `structlog.get_logger(__name__)` for logging
- Per-operation isolation in chain processing (same as B09's per-action pattern)
- Independent commits per record (D13)
- `from datetime import UTC, datetime` + `datetime.now(UTC)` (ruff UP017)
- `-> None` methods: bare `await adapter.method()`, never `result = await ...`
- Service test mocking: `MagicMock()` for ORM models, `db.execute.side_effect` for sequential mocks
- `mapped_column(default=uuid.uuid4)` is INSERT-time only → explicit `id=uuid.uuid4()` in constructor calls

## Open questions from SCRATCHPAD (resolve during implementation)

- `dict[str, str]` vs `list[FieldUpdate]` for `field_updates` → spec uses `dict[str, str]` (documented exception)
- Sentinel review needed: CRMAuthError no-retry in Celery task — risk of silencing config problems
- Async/sync boundary: Celery task is sync, service + adapter are async → need `asyncio.run()` wrapper

## Quality gates (must pass before commit)

```bash
python -m mypy src/services/schemas/crm_sync.py
python -m mypy src/services/crm_sync.py
python -m mypy src/tasks/crm_sync_task.py
python -m ruff check src/services/crm_sync.py src/services/schemas/crm_sync.py src/tasks/crm_sync_task.py
python -m ruff format src/services/ src/tasks/crm_sync_task.py --check
pytest tests/unit/test_crm_sync_schemas.py -v
pytest tests/unit/test_crm_sync_service.py -v
pytest tests/unit/test_crm_sync_task.py -v
pytest tests/ -q  # full non-integration suite
# Privacy verification (manual):
grep -r "body_plain\|body_html" src/services/crm_sync.py  # must return EMPTY
grep -r "body_plain\|body_html" src/tasks/crm_sync_task.py  # must return EMPTY
bash scripts/validate-docs.sh
```

## Style rules

- snake_case files/vars/functions, PascalCase classes
- Type hints on public functions, no `dict[str, Any]` at boundaries
- Contract docstrings: Preconditions, Guarantees, Errors raised, Errors silenced
- `structlog.get_logger(__name__)` — no `# type: ignore` needed
- Commit: `feat(crm-sync): block-10 — CRM sync service, N tests`
