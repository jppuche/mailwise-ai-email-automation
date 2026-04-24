# Block 03: Gmail Adapter — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-03-email-adapter.md` (218 lines, Spanish).

## What to build

`src/adapters/email/` — EmailAdapter ABC + GmailAdapter concrete impl.

### Files to create

| File | Purpose |
|------|---------|
| `src/adapters/email/exceptions.py` | Error hierarchy (EmailAdapterError base) |
| `src/adapters/email/schemas.py` | Typed contracts: EmailMessage, DraftId, Label, etc. |
| `src/adapters/email/base.py` | ABC with 7 abstract methods |
| `src/adapters/email/gmail.py` | GmailAdapter (google-api-python-client) |
| `src/adapters/email/__init__.py` | Public exports |

### Files to modify

| File | Change |
|------|--------|
| `src/core/config.py` | Add `gmail_max_results: int = 100` |
| `pyproject.toml` | Verify google deps already present |

## ABC methods (7)

```python
connect(credentials: EmailCredentials) -> ConnectionStatus
fetch_new_messages(since: datetime, limit: int) -> list[EmailMessage]
mark_as_processed(message_id: str) -> None
create_draft(to: str, subject: str, body: str, in_reply_to: str | None) -> DraftId
get_labels() -> list[Label]
apply_label(message_id: str, label_id: str) -> None
test_connection() -> ConnectionTestResult  # silences ALL errors, health-check semantics
```

## Critical decisions (from SCRATCHPAD)

- Deduplication in **calling service**, NOT adapter
- `test_connection()` silences all errors (returns status, never raises)
- Gmail threads ≠ messages — extraction documented in docstring
- `GMAIL_MAX_RESULTS` configurable (Cat 8), default 100
- Token refresh: `credentials.refresh(Request())` + persist

## Exception strategy (try-except D7)

- Each Gmail API call: `try/except HttpError` by status code
- Parse failures: per-message try/except, log + continue batch
- Validation errors: `if/raise ValueError`, NOT try/except
- No bare `except Exception` (except `test_connection`)

## Existing code you need to know

### Settings pattern — `src/core/config.py`

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    gmail_client_id: str = Field(default="")
    gmail_client_secret: str = Field(default="")
    gmail_redirect_uri: str = Field(default="http://localhost:8000/api/v1/auth/gmail/callback")
    # ... other fields
def get_settings() -> Settings:
    return Settings()
```

### Domain exceptions — `src/core/exceptions.py`

5 existing: `InvalidStateTransitionError`, `CategoryNotFoundError`, `DuplicateEmailError`, `AuthenticationError`, `AuthorizationError`. Block 03 adds its own in `adapters/email/exceptions.py`.

### Email model — `src/models/email.py`

EmailMessage schema fields must map to these columns:

```python
provider_message_id: str    # unique, Gmail's message ID
thread_id: str | None
account: str                # email account identifier
sender_email: str
sender_name: str | None
recipients: list[RecipientData]  # JSONB [{email, name, type}]
subject: str
body_plain: str | None
body_html: str | None
snippet: str | None         # max 500 chars
date: datetime
attachments: list[AttachmentData]  # JSONB [{filename, mime_type, size_bytes}]
provider_labels: list[str]
state: EmailState           # default FETCHED
```

TypedDicts: `RecipientData(email, name, type)`, `AttachmentData(filename, mime_type, size_bytes)`

### Adapter pattern — `src/adapters/redis_client.py` (reference impl)

```python
# Lazy singleton, structured try/except, custom error wrapping
_redis_client: aioredis.Redis | None = None
async def _get_redis() -> aioredis.Redis: ...  # lazy init from Settings

async def set_refresh_token(token, user_id, ttl_days) -> None:
    try:
        client = await _get_redis()
        await client.setex(...)
    except RedisConnectionError as exc:
        raise RedisClientError(...) from exc
    except RedisTimeoutError as exc:
        raise RedisClientError(...) from exc
```

### Test fixture pattern — `tests/integration/conftest.py`

- `migrated_db_module` — alembic upgrade head, module-scoped
- `override_db` — NullPool engine + `app.dependency_overrides[get_async_db]`
- `async_client` — httpx ASGITransport, no real HTTP
- `reset_redis_singleton` — autouse, resets `_redis_client = None` per test

## Quality gates (must pass before commit)

```bash
python -m ruff check src/
python -m ruff format src/ --check
python -m mypy src/
python -m pytest tests/ -q              # unit (no Docker)
python -m pytest tests/ --run-integration  # needs docker compose up db redis
```

## Style rules

- snake_case files/vars/functions, PascalCase classes
- Type hints on public functions, no `dict[str, Any]` at boundaries
- Contract docstrings: invariants, guarantees, errors raised, state transitions
- `# noqa: B008` on FastAPI `Depends()` in defaults
- `# type: ignore[no-untyped-call]` for untyped third-party methods
- Commit: `feat(email): block-03 — Gmail adapter, ABC, N tests`
