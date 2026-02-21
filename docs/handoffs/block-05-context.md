# Block 05: Channel Adapter (Slack) — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-05-channel-adapter.md`.

## What to build

`src/adapters/channel/` — ChannelAdapter ABC + SlackAdapter concrete impl + Block Kit formatter.

### Files to create

| File | Purpose |
|------|---------|
| `src/adapters/channel/exceptions.py` | Error hierarchy (ChannelAdapterError base) |
| `src/adapters/channel/schemas.py` | Typed contracts: RoutingPayload, DeliveryResult, Destination, etc. |
| `src/adapters/channel/formatters.py` | SlackBlockKitFormatter: RoutingPayload → Slack blocks (pure local, NO I/O) |
| `src/adapters/channel/base.py` | ABC with 4 abstract methods |
| `src/adapters/channel/slack.py` | SlackAdapter (slack-sdk AsyncWebClient) |
| `src/adapters/channel/__init__.py` | Public exports |

### Files to modify

| File | Change |
|------|--------|
| `src/core/config.py` | Add `channel_snippet_length`, `channel_subject_max_length`, `channel_slack_timeout_seconds`, `channel_destinations_page_size` |
| `pyproject.toml` | Verify slack-sdk already present |

## ABC methods (4)

```python
async def connect(credentials: ChannelCredentials) -> ConnectionStatus
async def send_notification(payload: RoutingPayload) -> DeliveryResult
async def test_connection() -> ConnectionTestResult  # silences ALL errors
async def get_available_destinations() -> list[Destination]
```

## Critical decisions (from SCRATCHPAD)

- `SlackApiError` classified by `response["error"]` string (Slack returns 200 OK on errors)
- `SlackBlockKitFormatter` is pure local computation — 0 try/except, 0 I/O
- `test_connection()` silences ALL errors (health-check semantics, `# noqa: BLE001`)
- HTTP 429: slack-sdk handles retries internally; adapter catches exhausted-retries case
- Snippet truncated by formatter (not adapter, not service) — `CHANNEL_SNIPPET_LENGTH` default 150
- `assigned_to=None` → "Unassigned" in Block Kit output
- Priority colors as module constants, not magic strings (Cat 3 pre-mortem)

## Exception hierarchy

```python
ChannelAdapterError(Exception)                # base, has original_error: Exception | None
  ChannelAuthError(ChannelAdapterError)       # invalid_auth, token_revoked, missing_scope
  ChannelRateLimitError(ChannelAdapterError)  # 429, has retry_after_seconds: int | None
  ChannelConnectionError(ChannelAdapterError) # network timeout, DNS failure
  ChannelDeliveryError(ChannelAdapterError)   # channel_not_found, is_archived, not_in_channel
```

## Exception strategy (try-except D7/D8)

- Slack API calls (`AsyncWebClient.*`): `try/except` with specific types
  - `SlackApiError` → inspect `response["error"]` to classify:
    - `{"invalid_auth", "token_revoked", "missing_scope"}` → `ChannelAuthError`
    - `{"channel_not_found", "is_archived", "not_in_channel"}` → `ChannelDeliveryError`
    - HTTP 429 (after SDK exhausts retries) → `ChannelRateLimitError`
    - anything else → `ChannelDeliveryError`
  - `asyncio.TimeoutError` → `ChannelConnectionError`
  - `aiohttp.ClientConnectionError` → `ChannelConnectionError`
- Block Kit construction (`formatters.py`): conditionals ONLY, NO try/except (D8)
- Validation: `if/raise ValueError`, NOT try/except
- No bare `except Exception` (except `test_connection`)

## Schemas (Pydantic)

```python
class SenderInfo(BaseModel):
    email: str
    name: str | None = None

class ClassificationInfo(BaseModel):
    action: str
    type: str
    confidence: Literal["high", "low"]

class RoutingPayload(BaseModel):
    email_id: str
    subject: str
    sender: SenderInfo
    classification: ClassificationInfo
    priority: Literal["urgent", "normal", "low"]
    snippet: str
    dashboard_link: str
    assigned_to: str | None = None
    timestamp: datetime

class Destination(BaseModel):
    id: str                                     # Slack channel ID (C...) or user ID (U...)
    name: str                                   # readable name (#general, @john)
    type: Literal["channel", "dm", "group"]

class ChannelCredentials(BaseModel):
    bot_token: str                              # xoxb-... for Slack

class ConnectionStatus(BaseModel):
    connected: bool
    workspace_name: str | None = None
    bot_user_id: str | None = None
    error: str | None = None

class ConnectionTestResult(BaseModel):
    success: bool
    workspace_name: str | None = None
    latency_ms: int
    error_detail: str | None = None

class DeliveryResult(BaseModel):
    success: bool
    message_ts: str | None = None               # Slack message timestamp (thread replies)
    channel_id: str | None = None
    error_detail: str | None = None
```

## Block Kit formatter (formatters.py — pure local computation)

### Priority constants (Cat 3: no magic strings)

```python
PRIORITY_COLORS: dict[str, str] = {
    "urgent": "#E01E5A",   # Slack red
    "normal": "#36C5F0",   # Slack blue
    "low":    "#9BA3AF",   # grey
}
PRIORITY_EMOJIS: dict[str, str] = {
    "urgent": ":red_circle:",
    "normal": ":large_blue_circle:",
    "low":    ":white_circle:",
}
```

### Expected Block Kit structure

4 blocks: `header` → `section` (fields) → `context` (snippet) → `actions` (dashboard button).

Invariants:
- `assigned_to=None` → field shows "Unassigned"
- Snippet truncated to `CHANNEL_SNIPPET_LENGTH` (default 150)
- Subject truncated to `CHANNEL_SUBJECT_MAX_LENGTH` (default 100, Slack limit)
- Sender format: `{name} <{email}>` if name present, `{email}` if not
- Method signature: `build_blocks(payload: RoutingPayload) -> list[dict[str, object]]`
- Pure function — 0 I/O, 0 try/except

## Existing code you need to know

### Settings pattern — `src/core/config.py`

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # Slack (existing)
    slack_bot_token: str = Field(default="")
    slack_signing_secret: str = Field(default="")
    # ... needs: channel_snippet_length, channel_subject_max_length,
    #            channel_slack_timeout_seconds, channel_destinations_page_size
```

### Adapter pattern (B03 email + B04 LLM — replicate this structure)

```
src/adapters/email/                     src/adapters/llm/
├── exceptions.py  # base + subclasses  ├── exceptions.py
├── schemas.py     # Pydantic models    ├── schemas.py
├── base.py        # ABC                ├── base.py
├── gmail.py       # concrete           ├── litellm_adapter.py
└── __init__.py    # re-exports         └── __init__.py
```

Key patterns to replicate:
- `original_error: Exception | None` field on base exception
- Contract-docstrings (4 questions) on each ABC method
- `# noqa: BLE001` on `test_connection()` bare except
- Module-level docstring with `contract-docstrings:` and `try-except D7:` tags
- `structlog.get_logger(__name__)` for logging
- `__all__` in `__init__.py` with sorted exports

### Exception pattern — `src/adapters/llm/exceptions.py`

```python
class LLMAdapterError(Exception):
    original_error: Exception | None
    def __init__(self, message: str, *, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error

class LLMRateLimitError(LLMAdapterError):
    retry_after_seconds: int | None
    def __init__(self, message: str, *, retry_after_seconds: int | None = None,
                 original_error: Exception | None = None) -> None:
        super().__init__(message, original_error=original_error)
        self.retry_after_seconds = retry_after_seconds
```

### Domain exceptions — `src/core/exceptions.py`

5 existing: `InvalidStateTransitionError`, `CategoryNotFoundError`, `DuplicateEmailError`, `AuthenticationError`, `AuthorizationError`. Block 05 adds its own hierarchy in `adapters/channel/exceptions.py`.

### Dependencies — `pyproject.toml`

`slack-sdk>=3.33` — should already be present. Check mypy override for `slack_sdk.*`.

### Test patterns (from B03/B04)

- `tests/unit/test_gmail_adapter.py` — reference for mocking SDK: `MagicMock` service, class-based grouping
- `tests/unit/test_litellm_adapter.py` — reference for `AsyncMock` + `@patch` on async SDK calls
- `tests/contract/test_llm_adapter_contract.py` — MockAdapter implementing ABC, verify return types + ValueError contracts
- Root `conftest.py`: `--run-integration` flag, `integration` marker
- `asyncio_mode = "auto"` in pyproject.toml

### Slack SDK mocking pattern

```python
from unittest.mock import AsyncMock, MagicMock, patch
from slack_sdk.errors import SlackApiError

@pytest.fixture
def mock_client() -> AsyncMock:
    """Mock AsyncWebClient."""
    client = AsyncMock()
    # auth.test response
    client.auth_test.return_value = {
        "ok": True,
        "team": "Test Workspace",
        "user_id": "U123BOT",
    }
    # chat.postMessage response
    client.chat_postMessage.return_value = {
        "ok": True,
        "ts": "1234567890.123456",
        "channel": "C123CHANNEL",
    }
    return client

def _make_slack_api_error(error_code: str) -> SlackApiError:
    """Build a SlackApiError with a specific error code."""
    response = MagicMock()
    response.get.return_value = error_code
    response.__getitem__ = lambda self, key: error_code if key == "error" else None
    response.status_code = 200  # Slack returns 200 on most errors
    return SlackApiError(message=f"Error: {error_code}", response=response)

def _make_slack_rate_limit_error() -> SlackApiError:
    """Build a SlackApiError for HTTP 429."""
    response = MagicMock()
    response.get.return_value = "ratelimited"
    response.__getitem__ = lambda self, key: "ratelimited" if key == "error" else None
    response.status_code = 429
    response.headers = {"Retry-After": "30"}
    return SlackApiError(message="Rate limited", response=response)
```

**IMPORTANT**: `SlackApiError` constructor takes `message` and `response` kwargs. The `response` must support `.get("error")` and `.status_code`. Verify constructor signature before writing tests.

## Load-bearing defaults (Cat 8)

| Default | Value | Env Var | Risk if wrong |
|---------|-------|---------|---------------|
| Snippet length | `150` | `CHANNEL_SNIPPET_LENGTH` | Too long: Slack message visually overloaded |
| Subject max length | `100` | `CHANNEL_SUBJECT_MAX_LENGTH` | Hard limit in Slack `plain_text` header block |
| Slack API timeout | `10`s | `CHANNEL_SLACK_TIMEOUT_SECONDS` | Too low: false timeouts on slow network |
| Destinations page size | `200` | `CHANNEL_DESTINATIONS_PAGE_SIZE` | Slack API limit for `conversations.list` |

## SlackApiError → exception mapping table

| Slack error code | Adapter exception |
|------------------|-------------------|
| `invalid_auth` | `ChannelAuthError` |
| `token_revoked` | `ChannelAuthError` |
| `missing_scope` | `ChannelAuthError` |
| `channel_not_found` | `ChannelDeliveryError` |
| `is_archived` | `ChannelDeliveryError` |
| `not_in_channel` | `ChannelDeliveryError` |
| `cant_invite_self` | `ChannelDeliveryError` |
| HTTP 429 (`ratelimited`) | `ChannelRateLimitError` |
| any other | `ChannelDeliveryError` |

## Quality gates (must pass before commit)

```bash
python -m mypy src/adapters/channel/
python -m ruff check src/adapters/channel/
python -m ruff format src/adapters/channel/ --check
pytest tests/unit/test_channel_schemas.py -v
pytest tests/unit/test_channel_formatters.py -v
pytest tests/unit/test_slack_adapter.py -v
pytest tests/contract/test_channel_adapter_contract.py -v
pytest tests/ -q                    # full non-integration suite
bash scripts/validate-docs.sh
```

## Style rules

- snake_case files/vars/functions, PascalCase classes
- Type hints on public functions, no `dict[str, Any]` at boundaries
- Contract docstrings: invariants, guarantees, errors raised, state transitions
- `# noqa: BLE001` on `test_connection()` bare except
- `datetime.UTC` not `timezone.utc` (ruff UP017)
- Commit: `feat(channel): block-05 — Slack adapter, Block Kit formatter, N tests`
