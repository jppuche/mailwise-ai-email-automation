# Block 06: CRM Adapter (HubSpot) — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-06-crm-adapter.md`.

## What to build

`src/adapters/crm/` — CRMAdapter ABC + HubSpotAdapter concrete impl + structured HubSpot error mapping.

### Files to create

| File | Purpose |
|------|---------|
| `src/adapters/crm/exceptions.py` | Error hierarchy (CRMAdapterError base + 6 subclasses) |
| `src/adapters/crm/schemas.py` | Typed contracts: Contact, CreateContactData, ActivityData, ActivityId, LeadId, etc. |
| `src/adapters/crm/base.py` | ABC with 7 abstract methods |
| `src/adapters/crm/hubspot.py` | HubSpotAdapter (hubspot-api-client SDK) |
| `src/adapters/crm/__init__.py` | Public exports |

### Files to modify

| File | Change |
|------|--------|
| `src/core/config.py` | Add `hubspot_rate_limit_per_10s`, `hubspot_activity_snippet_length`, `hubspot_auto_create_contacts`, `hubspot_default_lead_status`, `hubspot_api_timeout_seconds` |

## ABC methods (7)

```python
async def connect(credentials: CRMCredentials) -> ConnectionStatus
async def lookup_contact(email: str) -> Contact | None
async def create_contact(data: CreateContactData) -> Contact
async def log_activity(contact_id: str, activity: ActivityData) -> ActivityId
async def create_lead(data: CreateLeadData) -> LeadId
async def update_field(contact_id: str, field: str, value: str) -> None
async def test_connection() -> ConnectionTestResult  # silences ALL errors
```

## CRITICAL: HubSpot SDK is SYNC-ONLY

`hubspot-api-client` has NO async support. All SDK methods are synchronous.

**Solution**: Wrap every SDK call with `asyncio.to_thread()`:
```python
response = await asyncio.to_thread(
    self._client.crm.contacts.search_api.do_search,
    public_object_search_request={...}
)
```

The ABC methods are `async def` (consistent with channel/LLM adapters), but the underlying SDK calls must be wrapped. This is the standard pattern for sync SDKs in async contexts.

## Critical decisions (from SCRATCHPAD + spec)

- `ActivityId`/`LeadId` as `NewType("ActivityId", str)` — semantic distinction, not Pydantic model
- Duplicate contacts in `lookup_contact`: use most recent by `createdate`, log ambiguity
- Snippet truncated by calling SERVICE, not adapter — adapter receives pre-truncated data
- `update_field` silences `FieldNotFoundError` per Sec 6.4 (log + skip, no fail)
- `CRMAuthError`: no retry (in Celery tasks). Caller decides retry strategy
- `dict[str, str]` for `field_updates` is a documented exception to the no-dict rule (SCRATCHPAD B10)
- `contact_id` always `str` — HubSpot uses numeric IDs as strings, never convert to `int`
- PII policy: logger NEVER logs snippet, subject, or sender data — only IDs
- `_raise_from_hubspot_exc()` is a module-level helper (not a method) — classifies `ApiException` by `.status`

## Exception hierarchy

```python
CRMAdapterError(Exception)                    # base, has original_error: Exception | None
  CRMAuthError(CRMAdapterError)              # HTTP 401
  CRMRateLimitError(CRMAdapterError)         # HTTP 429, has retry_after_seconds: int | None
  CRMConnectionError(CRMAdapterError)        # network, timeout, DNS, 5xx
  DuplicateContactError(CRMAdapterError)     # HTTP 409
  ContactNotFoundError(CRMAdapterError)      # HTTP 404
  FieldNotFoundError(CRMAdapterError)        # HTTP 400 + PROPERTY_DOESNT_EXIST
```

**IMPORTANT**: The spec's exception skeleton omits `original_error`. Add it for consistency with B03/B04/B05 adapters.

## Exception strategy (try-except D7/D8)

- HubSpot SDK calls (`self._client.crm.*`): `try/except ApiException` with status-based classification
  - Use `_raise_from_hubspot_exc(exc)` helper for consistent mapping
  - HTTP 401 → `CRMAuthError`
  - HTTP 404 → `ContactNotFoundError`
  - HTTP 409 → `DuplicateContactError`
  - HTTP 429 → `CRMRateLimitError`
  - HTTP 400 + `PROPERTY_DOESNT_EXIST` in body → `FieldNotFoundError` (silenced in `update_field`)
  - All others → `CRMConnectionError`
- SDK-to-Pydantic mapping: conditionals ONLY, NO try/except (D8)
- Validation: `if/raise ValueError`, NOT try/except
- No bare `except Exception` (except `test_connection`)

## HubSpot SDK import paths

```python
import hubspot
from hubspot.crm.contacts.exceptions import ApiException

# Create client
client = hubspot.HubSpot(access_token="...")

# Search contacts
response = client.crm.contacts.search_api.do_search(
    public_object_search_request={...}
)

# Create contact
response = client.crm.contacts.basic_api.create(
    simple_public_object_input_for_create={"properties": {...}}
)

# Update contact
client.crm.contacts.basic_api.update(
    contact_id="12345",
    simple_public_object_input={"properties": {field: value}}
)

# Create note (for log_activity)
client.crm.objects.notes.basic_api.create(
    simple_public_object_input_for_create={"properties": {...}}
)

# Associate note to contact
client.crm.objects.notes.associations_api.create(
    note_id="...", to_object_type="contacts", to_object_id="...",
    association_type=[{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]
)

# Create deal (for create_lead)
client.crm.deals.basic_api.create(
    simple_public_object_input_for_create={"properties": {...}}
)

# Test connection (account info)
response = client.crm.contacts.basic_api.get_page(limit=1)
```

**SDK response objects**: `SimplePublicObject` with `.id` (str) and `.properties` (dict). These objects NEVER cross the adapter boundary — extract into Pydantic models inside `hubspot.py`.

## Schemas (Pydantic)

```python
from typing import NewType
from pydantic import BaseModel, field_validator

ActivityId = NewType("ActivityId", str)
LeadId = NewType("LeadId", str)

class CRMCredentials(BaseModel):
    access_token: str                      # HubSpot Private App Token

class ConnectionStatus(BaseModel):
    connected: bool
    portal_id: str | None = None
    account_name: str | None = None
    error: str | None = None

class ConnectionTestResult(BaseModel):
    success: bool
    portal_id: str | None = None
    latency_ms: int
    error_detail: str | None = None

class Contact(BaseModel):
    id: str                                # numeric HubSpot ID as str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

class CreateContactData(BaseModel):
    email: str
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    source: str | None = None
    first_interaction_at: datetime | None = None

    @field_validator("email")
    @classmethod
    def email_must_have_at(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("email must contain '@'")
        return v

class ActivityData(BaseModel):
    subject: str
    timestamp: datetime                    # timezone-aware
    classification_action: str
    classification_type: str
    snippet: str                           # pre-truncated by calling service
    email_id: str
    dashboard_link: str | None = None

class CreateLeadData(BaseModel):
    contact_id: str
    summary: str
    source: str
    lead_status: str = "NEW"
```

## Existing code you need to know

### Settings pattern — `src/core/config.py`

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # HubSpot (existing)
    hubspot_access_token: str = Field(default="")
    # ... needs: hubspot_rate_limit_per_10s, hubspot_activity_snippet_length,
    #            hubspot_auto_create_contacts, hubspot_default_lead_status,
    #            hubspot_api_timeout_seconds
```

### Adapter pattern (B03 email + B04 LLM + B05 channel — replicate this structure)

```
src/adapters/channel/                    src/adapters/llm/
├── exceptions.py  # base + subclasses  ├── exceptions.py
├── schemas.py     # Pydantic models    ├── schemas.py
├── base.py        # ABC                ├── base.py
├── slack.py       # concrete           ├── litellm_adapter.py
├── formatters.py  # pure local         └── __init__.py
└── __init__.py    # re-exports
```

Key patterns to replicate:
- `original_error: Exception | None` field on base exception (keyword-only)
- Contract-docstrings (4 questions) on each ABC method
- `# noqa: BLE001` on `test_connection()` bare except
- Module-level docstring with `contract-docstrings:` and `try-except D7:` tags
- `structlog.get_logger(__name__)` for logging (no `# type: ignore` needed)
- `__all__` in `__init__.py` with sorted exports
- `_ensure_connected()` helper + `assert self._client is not None` for mypy narrowing

### Exception pattern — `src/adapters/channel/exceptions.py`

```python
class ChannelAdapterError(Exception):
    original_error: Exception | None
    def __init__(self, message: str, *, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error

class ChannelRateLimitError(ChannelAdapterError):
    retry_after_seconds: int | None
    def __init__(self, message: str, *, retry_after_seconds: int | None = None,
                 original_error: Exception | None = None) -> None:
        super().__init__(message, original_error=original_error)
        self.retry_after_seconds = retry_after_seconds
```

### Dependencies — `pyproject.toml`

`hubspot-api-client>=9.0` — already present. `hubspot.*` already in mypy overrides. No pyproject.toml changes needed except optional version pin tightening (Cat 10 exit criterion).

### Test patterns (from B03/B04/B05)

- Tests go in `tests/unit/` (flat) and `tests/contract/` — NOT in subdirectories
  - **Note**: spec says `tests/adapters/crm/` but actual convention is flat `tests/unit/`
  - Use: `tests/unit/test_crm_schemas.py`, `tests/unit/test_hubspot_adapter.py`, `tests/contract/test_crm_adapter_contract.py`
- `asyncio_mode = "auto"` in pyproject.toml — `async def test_*` works without decorator
- Root `conftest.py`: `--run-integration` flag, `integration` marker
- HubSpot SDK is sync → mock with `MagicMock`, NOT `AsyncMock`
  - But `asyncio.to_thread()` wraps them → patch `asyncio.to_thread` or the SDK method directly
- `_make_api_exception()` helper (analogous to `_make_slack_api_error()`)

### HubSpot SDK mocking pattern

```python
from unittest.mock import MagicMock, patch
from hubspot.crm.contacts.exceptions import ApiException

@pytest.fixture
def mock_hubspot_client() -> MagicMock:
    """Mock hubspot.HubSpot() client."""
    client = MagicMock()
    # contacts.search_api.do_search
    search_result = MagicMock()
    search_result.results = []
    client.crm.contacts.search_api.do_search.return_value = search_result
    # contacts.basic_api.create
    created = MagicMock()
    created.id = "12345"
    created.properties = {"email": "alice@example.com", "firstname": "Alice"}
    client.crm.contacts.basic_api.create.return_value = created
    # contacts.basic_api.get_page (for test_connection)
    page = MagicMock()
    page.results = []
    client.crm.contacts.basic_api.get_page.return_value = page
    return client

def _make_api_exception(status: int, reason: str = "", body: str = "") -> ApiException:
    """Build an ApiException with a specific status."""
    exc = ApiException(status=status, reason=reason)
    exc.body = body
    return exc
```

**IMPORTANT**: Patch `hubspot.HubSpot` at the import site:
```python
@patch("src.adapters.crm.hubspot.hubspot.HubSpot", return_value=mock_hubspot_client)
```

Or if the adapter stores the client from `connect()`:
```python
adapter._client = mock_hubspot_client  # inject directly after connect
```

### `asyncio.to_thread` mocking strategy

Since all SDK calls go through `asyncio.to_thread()`, there are two approaches:

**Option A**: Patch `asyncio.to_thread` to just call the function directly (simpler):
```python
@pytest.fixture(autouse=True)
def mock_to_thread(monkeypatch):
    """Make asyncio.to_thread run synchronously in tests."""
    async def _sync_to_thread(func, /, *args, **kwargs):
        return func(*args, **kwargs)
    monkeypatch.setattr("asyncio.to_thread", _sync_to_thread)
```

**Option B**: Patch the SDK methods directly — `asyncio.to_thread` calls through transparently.

Option A is recommended — simpler, less coupling to SDK internals.

## Load-bearing defaults (Cat 8)

| Default | Value | Env Var | Risk if wrong |
|---------|-------|---------|---------------|
| Rate limit (free tier) | `100` req/10s | `HUBSPOT_RATE_LIMIT_PER_10S` | Exceeding causes 429 cascade |
| Activity snippet length | `200` chars | `HUBSPOT_ACTIVITY_SNIPPET_LENGTH` | PII risk if too long |
| Auto-create contacts | `false` | `HUBSPOT_AUTO_CREATE_CONTACTS` | `true` creates spam contacts |
| Default lead status | `"NEW"` | `HUBSPOT_DEFAULT_LEAD_STATUS` | Wrong status = unmonitored leads |
| API timeout | `15`s | `HUBSPOT_API_TIMEOUT_SECONDS` | Too low: false timeouts |

## HubSpot error → exception mapping table

| HTTP status | Body condition | Adapter exception |
|-------------|---------------|-------------------|
| `401` | any | `CRMAuthError` |
| `404` | any | `ContactNotFoundError` |
| `409` | any | `DuplicateContactError` |
| `429` | any | `CRMRateLimitError` |
| `400` | `PROPERTY_DOESNT_EXIST` in body | `FieldNotFoundError` (silenced in `update_field`) |
| `400` | other | `CRMConnectionError` |
| `5xx` | any | `CRMConnectionError` |
| network/timeout | N/A | `CRMConnectionError` |

## Privacy (Sec 6.5 — MANDATORY)

- Adapter NEVER receives full email body — only `snippet` (pre-truncated by service)
- `ActivityData` has NO `body` or `body_plain` field
- Logger in `hubspot.py` NEVER logs `snippet`, `subject`, or sender data — only IDs
- `_hash_email()` helper for logging lookup queries (SHA-256 of email, not raw email)

## update_field silencing pattern

```python
async def update_field(self, contact_id: str, field: str, value: str) -> None:
    if not contact_id or not field:
        raise ValueError("contact_id and field must not be empty")
    self._ensure_connected()

    try:
        await asyncio.to_thread(
            self._client.crm.contacts.basic_api.update,
            contact_id=contact_id,
            simple_public_object_input={"properties": {field: value}},
        )
    except ApiException as exc:
        # FieldNotFoundError silenced per Sec 6.4 (log, skip, no fail)
        if exc.status == 400 and "PROPERTY_DOESNT_EXIST" in (exc.body or ""):
            logger.warning("crm_field_not_found", contact_id=contact_id, field=field)
            return
        raise _raise_from_hubspot_exc(exc) from exc
```

## lookup_contact ambiguity handling

```python
# Search with limit=2 to detect ambiguity
request = {
    "filterGroups": [
        {"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}
    ],
    "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
    "limit": 2,
}
# If len(results) > 1: log warning with count, use results[0] (most recent)
# If len(results) == 0: return None
```

## Quality gates (must pass before commit)

```bash
python -m mypy src/adapters/crm/
python -m ruff check src/adapters/crm/
python -m ruff format src/adapters/crm/ --check
pytest tests/unit/test_crm_schemas.py -v
pytest tests/unit/test_hubspot_adapter.py -v
pytest tests/contract/test_crm_adapter_contract.py -v
pytest tests/ -q                    # full non-integration suite
bash scripts/validate-docs.sh
```

## Style rules

- snake_case files/vars/functions, PascalCase classes
- Type hints on public functions, no `dict[str, Any]` at boundaries
- Contract docstrings: Preconditions, Guarantees, Errors raised, Errors silenced
- `# noqa: BLE001` on `test_connection()` bare except
- `TimeoutError` not `asyncio.TimeoutError` (ruff UP041)
- `contextlib.suppress` not `try/except/pass` (ruff SIM105)
- `structlog.get_logger(__name__)` — no `# type: ignore` needed
- Commit: `feat(crm): block-06 — HubSpot adapter, 7 methods, N tests`
