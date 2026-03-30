# Adapter Extension Guide — mailwise

## Glossary: Class names to integration names

| Class / Module | User-visible name | Current implementation |
|----------------|-------------------|------------------------|
| `EmailAdapter` | Email Provider | Gmail (`src/adapters/email/gmail.py`) |
| `ChannelAdapter` | Notification Channel | Slack (`src/adapters/channel/slack.py`) |
| `CRMAdapter` | CRM Integration | HubSpot (`src/adapters/crm/hubspot.py`) |
| `LLMAdapter` | AI Model | LiteLLM/OpenAI (`src/adapters/llm/litellm.py`) |

---

## Overview

mailwise uses the Adapter pattern (FOUNDATION.md Sec 9) to isolate all external integrations. Each adapter family has:

- **An ABC** (`base.py`) — defines the typed interface
- **A concrete implementation** — one per provider (e.g. `gmail.py`, `slack.py`)
- **Schemas** (`schemas.py`) — Pydantic models that form the type boundary
- **Exceptions** (`exceptions.py`) — domain-typed errors (never raw HTTP status codes)

The rule: raw provider objects (Gmail dicts, Slack API responses, HubSpot SDK models, LiteLLM `ModelResponse`) **never cross the adapter boundary**. Only typed schemas from `adapters.<family>.schemas` leave the adapter layer.

### Adding a new provider

Each adapter family follows the same 5-step pattern:

1. Implement the ABC in a new file
2. Register the provider name in the relevant config key
3. Wire it into the DI factory in `src/api/deps.py`
4. Add credentials to `.env.example`
5. Write an integration test

The sections below walk through each family with a realistic example.

---

## Email Adapter — adding Outlook

**ABC:** `src/adapters/email/base.py`
**Schemas:** `src/adapters/email/schemas.py`
**Exceptions:** `src/adapters/email/exceptions.py`

### Methods to implement

```python
class EmailAdapter(abc.ABC):
    def connect(self, credentials: EmailCredentials) -> ConnectionStatus: ...
    def fetch_new_messages(self, since: datetime, limit: int) -> list[EmailMessage]: ...
    def mark_as_processed(self, message_id: str) -> None: ...
    def create_draft(self, to: str, subject: str, body: str,
                     in_reply_to: str | None = None) -> DraftId: ...
    def get_labels(self) -> list[Label]: ...
    def apply_label(self, message_id: str, label_id: str) -> None: ...
    def test_connection(self) -> ConnectionTestResult: ...
```

Note: `EmailAdapter` methods are **synchronous** (unlike Channel, CRM, and LLM which are async). The ingestion service calls them from Celery tasks, which use `asyncio.run()` internally.

### Step 1: Implement the ABC

Create `src/adapters/email/outlook.py`:

```python
"""OutlookAdapter — EmailAdapter for Microsoft Graph API.

Invariants: OAuth2 credentials loaded via ``connect()``. Graph client
    initialized with ``MSAL`` token acquisition.
  Guarantees: All returned values are typed schemas — raw Graph API dicts
    stay inside this module. Deduplication is the caller's responsibility.
  Errors raised: Typed ``EmailAdapterError`` subclasses (see exceptions.py).
  Errors silenced: ``test_connection()`` silences all errors.
    ``fetch_new_messages()`` silences per-message parse failures.
  External state: Microsoft Graph API.
"""

from __future__ import annotations

import structlog
from datetime import UTC, datetime

import msal
import requests

from src.adapters.email.base import EmailAdapter
from src.adapters.email.exceptions import (
    AuthError,
    EmailConnectionError,
    FetchError,
    RateLimitError,
)
from src.adapters.email.schemas import (
    ConnectionStatus,
    ConnectionTestResult,
    DraftId,
    EmailCredentials,
    EmailMessage,
    Label,
)

logger = structlog.get_logger(__name__)

_GRAPH_ENDPOINT = "https://graph.microsoft.com/v1.0"


class OutlookAdapter(EmailAdapter):
    """Microsoft Outlook (Graph API) email adapter."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._account_email: str | None = None

    def _ensure_connected(self) -> None:
        if self._token is None:
            raise AuthError("OutlookAdapter.connect() has not been called")

    def connect(self, credentials: EmailCredentials) -> ConnectionStatus:
        """Acquire an access token via MSAL and verify identity.

        Invariants:
          - ``credentials.client_id``, ``credentials.client_secret``,
            ``credentials.refresh_token`` are non-empty.

        Guarantees:
          - On success, ``self._token`` is set and adapter is ready.
          - Returns ``ConnectionStatus(connected=True, account=email)``.

        Errors raised:
          - ``ValueError`` if a required credential field is empty.
          - ``AuthError`` if MSAL rejects the credentials.
          - ``EmailConnectionError`` on network failure during token exchange.

        Errors silenced: None.
        """
        if not credentials.client_id:
            raise ValueError("credentials.client_id is required")
        if not credentials.refresh_token:
            raise ValueError("credentials.refresh_token is required")

        app = msal.ConfidentialClientApplication(
            client_id=credentials.client_id,
            client_credential=credentials.client_secret,
            authority="https://login.microsoftonline.com/common",
        )
        try:
            result = app.acquire_token_by_refresh_token(
                credentials.refresh_token,
                scopes=["https://graph.microsoft.com/Mail.ReadWrite"],
            )
        except Exception as exc:
            raise EmailConnectionError(f"Token exchange failed: {exc}") from exc

        if "access_token" not in result:
            raise AuthError(f"MSAL error: {result.get('error_description')}")

        self._token = result["access_token"]
        # Retrieve authenticated user email
        me = requests.get(
            f"{_GRAPH_ENDPOINT}/me",
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=10,
        ).json()
        self._account_email = me.get("mail") or me.get("userPrincipalName", "")
        return ConnectionStatus(connected=True, account=self._account_email)

    def fetch_new_messages(
        self, since: datetime, limit: int
    ) -> list[EmailMessage]:
        """Fetch messages received after ``since``, up to ``limit``.

        Invariants:
          - ``since`` is timezone-aware UTC.
          - ``limit`` is in [1, 500].
          - Adapter is connected.

        Guarantees:
          - Returns ``list[EmailMessage]`` (may be empty).
          - Each ``EmailMessage.received_at`` is timezone-aware UTC.

        Errors raised:
          - ``ValueError`` if ``since`` is naive or ``limit`` is out of range.
          - ``AuthError`` on 401.
          - ``RateLimitError`` on 429.
          - ``EmailConnectionError`` on 5xx / network failure.

        Errors silenced:
          - Per-message parse failures (``KeyError``, ``ValueError``) are
            logged with ``message_id`` and skipped.
        """
        self._ensure_connected()
        assert self._token is not None

        if since.tzinfo is None:
            raise ValueError("'since' must be timezone-aware")
        if not 1 <= limit <= 500:
            raise ValueError("'limit' must be in [1, 500]")

        since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        url = (
            f"{_GRAPH_ENDPOINT}/me/messages"
            f"?$filter=receivedDateTime gt {since_iso}"
            f"&$top={limit}"
            f"&$select=id,subject,from,body,receivedDateTime,toRecipients"
        )
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise EmailConnectionError(f"Graph API network error: {exc}") from exc

        if response.status_code == 401:
            raise AuthError("Graph API 401 — token expired or revoked")
        if response.status_code == 429:
            raise RateLimitError("Graph API 429 — rate limit exceeded")
        if response.status_code >= 500:
            raise EmailConnectionError(f"Graph API {response.status_code}")

        messages: list[EmailMessage] = []
        for item in response.json().get("value", []):
            try:
                messages.append(self._parse_message(item))
            except (KeyError, ValueError) as exc:
                logger.warning(
                    "outlook.parse_skip",
                    message_id=item.get("id"),
                    error=str(exc),
                )
        return messages

    def _parse_message(self, item: dict) -> EmailMessage:  # type: ignore[type-arg]
        """Parse a Graph API message dict into EmailMessage."""
        return EmailMessage(
            gmail_message_id=item["id"],
            subject=item.get("subject", "(no subject)"),
            sender=item["from"]["emailAddress"]["address"],
            recipients=[r["emailAddress"]["address"]
                        for r in item.get("toRecipients", [])],
            body=item["body"]["content"],
            received_at=datetime.fromisoformat(
                item["receivedDateTime"].replace("Z", "+00:00")
            ),
        )

    def mark_as_processed(self, message_id: str) -> None:
        """Move message to a 'Processed' category via Graph API patch."""
        self._ensure_connected()
        assert self._token is not None

        if not message_id:
            raise ValueError("message_id is required")

        try:
            response = requests.patch(
                f"{_GRAPH_ENDPOINT}/me/messages/{message_id}",
                headers={"Authorization": f"Bearer {self._token}"},
                json={"categories": ["Processed"]},
                timeout=10,
            )
        except requests.RequestException as exc:
            raise EmailConnectionError(f"mark_as_processed failed: {exc}") from exc

        if response.status_code == 401:
            raise AuthError("Graph API 401")
        if response.status_code == 429:
            raise RateLimitError("Graph API 429")

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
    ) -> DraftId:
        """Create a draft in the Outlook Drafts folder."""
        self._ensure_connected()
        assert self._token is not None

        if "@" not in to:
            raise ValueError("'to' must contain '@'")
        if not body:
            raise ValueError("'body' is required")

        payload: dict = {  # type: ignore[type-arg]
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        }
        try:
            response = requests.post(
                f"{_GRAPH_ENDPOINT}/me/messages",
                headers={"Authorization": f"Bearer {self._token}"},
                json=payload,
                timeout=10,
            )
        except requests.RequestException as exc:
            raise EmailConnectionError(f"create_draft failed: {exc}") from exc

        if response.status_code not in (200, 201):
            raise EmailConnectionError(f"Draft creation failed: {response.status_code}")

        return DraftId(id=response.json()["id"])

    def get_labels(self) -> list[Label]:
        """List Outlook mail folders as labels."""
        self._ensure_connected()
        assert self._token is not None

        response = requests.get(
            f"{_GRAPH_ENDPOINT}/me/mailFolders",
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=10,
        )
        return [
            Label(id=f["id"], name=f["displayName"], type="user")
            for f in response.json().get("value", [])
        ]

    def apply_label(self, message_id: str, label_id: str) -> None:
        """Move message to the specified mail folder."""
        self._ensure_connected()
        assert self._token is not None

        if not message_id or not label_id:
            raise ValueError("message_id and label_id are required")

        requests.post(
            f"{_GRAPH_ENDPOINT}/me/messages/{message_id}/move",
            headers={"Authorization": f"Bearer {self._token}"},
            json={"destinationId": label_id},
            timeout=10,
        )

    def test_connection(self) -> ConnectionTestResult:
        """Ping the Graph /me endpoint. NEVER raises."""
        import time
        start = time.monotonic()
        try:
            if self._token is None:
                return ConnectionTestResult(connected=False, error="Not connected")
            response = requests.get(
                f"{_GRAPH_ENDPOINT}/me",
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=5,
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            if response.status_code == 200:
                return ConnectionTestResult(connected=True, latency_ms=latency_ms)
            return ConnectionTestResult(
                connected=False,
                error=f"HTTP {response.status_code}",
                latency_ms=latency_ms,
            )
        except Exception as exc:
            return ConnectionTestResult(connected=False, error=str(exc))
```

### Step 2: Register in config

Add to `src/core/config.py`:

```python
email_provider: str = Field(default="gmail")  # "gmail" | "outlook"
outlook_client_id: str = Field(default="")
outlook_client_secret: str = Field(default="")
```

### Step 3: Wire into DI factory

Update `src/api/deps.py` (or the ingestion service factory):

```python
from src.adapters.email.gmail import GmailAdapter
from src.adapters.email.outlook import OutlookAdapter

def get_email_adapter(settings: Settings) -> EmailAdapter:
    if settings.email_provider == "outlook":
        return OutlookAdapter()
    return GmailAdapter()
```

### Step 4: Add to .env.example

```bash
# --- Email Provider ---
# Default: gmail. Options: gmail | outlook
EMAIL_PROVIDER=gmail

# Outlook (Microsoft Graph API) — required if EMAIL_PROVIDER=outlook
OUTLOOK_CLIENT_ID=
OUTLOOK_CLIENT_SECRET=
```

### Step 5: Write integration test

```python
# tests/integration/test_outlook_adapter.py
import pytest
from src.adapters.email.outlook import OutlookAdapter
from src.adapters.email.schemas import EmailCredentials

@pytest.mark.integration
def test_outlook_connect_rejects_empty_client_id() -> None:
    adapter = OutlookAdapter()
    with pytest.raises(ValueError, match="client_id"):
        adapter.connect(EmailCredentials(
            client_id="",
            client_secret="secret",
            token="tok",
            refresh_token="rtok",
        ))

@pytest.mark.integration
def test_outlook_test_connection_never_raises() -> None:
    adapter = OutlookAdapter()
    result = adapter.test_connection()
    assert result.connected is False  # no token loaded
    assert result.error is not None
```

---

## Channel Adapter — adding Microsoft Teams

**ABC:** `src/adapters/channel/base.py`
**Schemas:** `src/adapters/channel/schemas.py`
**Exceptions:** `src/adapters/channel/exceptions.py`

### Methods to implement

```python
class ChannelAdapter(abc.ABC):
    async def connect(self, credentials: ChannelCredentials) -> ConnectionStatus: ...
    async def send_notification(self, payload: RoutingPayload,
                                destination_id: str) -> DeliveryResult: ...
    async def test_connection(self) -> ConnectionTestResult: ...
    async def get_available_destinations(self) -> list[Destination]: ...
```

Note: All Channel methods are **async** (unlike Email).

### Step 1: Implement the ABC

Create `src/adapters/channel/teams.py`:

```python
"""TeamsAdapter — ChannelAdapter for Microsoft Teams (Incoming Webhooks).

Invariants: Webhook URL loaded via ``connect()``. Webhook URL contains
    the channel and tenant identifiers.
  Guarantees: All returned values are typed schemas. Teams API dicts
    never leak past this adapter.
  Errors raised: Typed ``ChannelAdapterError`` subclasses (see exceptions.py).
  Errors silenced: ``test_connection()`` silences all errors.
  External state: Microsoft Teams Incoming Webhook API.
"""

from __future__ import annotations

import time

import httpx
import structlog

from src.adapters.channel.base import ChannelAdapter
from src.adapters.channel.exceptions import (
    ChannelAuthError,
    ChannelConnectionError,
    ChannelDeliveryError,
    ChannelRateLimitError,
)
from src.adapters.channel.schemas import (
    ChannelCredentials,
    ConnectionStatus,
    ConnectionTestResult,
    DeliveryResult,
    Destination,
    RoutingPayload,
)

logger = structlog.get_logger(__name__)


class TeamsAdapter(ChannelAdapter):
    """Microsoft Teams adapter using Incoming Webhooks."""

    def __init__(self) -> None:
        self._webhook_url: str | None = None

    def _ensure_connected(self) -> None:
        if self._webhook_url is None:
            raise ChannelAuthError("TeamsAdapter.connect() has not been called")

    async def connect(self, credentials: ChannelCredentials) -> ConnectionStatus:
        """Store the Teams webhook URL.

        Preconditions:
          - ``credentials.bot_token`` contains the full webhook URL
            (Teams adapters use webhook URLs as the token field).

        Guarantees:
          - On success, adapter is ready for subsequent operations.

        Errors raised:
          - ``ValueError`` if ``bot_token`` is empty or not a valid URL.
          - ``ChannelConnectionError`` on network failure during verification.

        Errors silenced: None.
        """
        if not credentials.bot_token:
            raise ValueError("credentials.bot_token (webhook URL) is required")
        if not credentials.bot_token.startswith("https://"):
            raise ValueError("Teams webhook URL must start with 'https://'")

        self._webhook_url = credentials.bot_token
        return ConnectionStatus(connected=True, account="teams-webhook")

    async def send_notification(
        self,
        payload: RoutingPayload,
        destination_id: str,
    ) -> DeliveryResult:
        """Send an Adaptive Card to the Teams channel via webhook.

        Preconditions:
          - ``destination_id`` is non-empty (ignored for webhooks — channel
            is encoded in the webhook URL).
          - ``payload.email_id`` is non-empty.
          - Adapter is connected.

        Guarantees:
          - On success, returns ``DeliveryResult(success=True)``.

        Errors raised:
          - ``ValueError`` if ``destination_id`` is empty.
          - ``ChannelRateLimitError`` on HTTP 429.
          - ``ChannelConnectionError`` on network / timeout failure.
          - ``ChannelDeliveryError`` on non-2xx response.

        Errors silenced: None.
        """
        self._ensure_connected()
        assert self._webhook_url is not None

        if not destination_id:
            raise ValueError("destination_id is required")

        card = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {"type": "TextBlock", "text": f"New email: {payload.subject}",
                         "weight": "Bolder"},
                        {"type": "TextBlock", "text": payload.snippet or "",
                         "wrap": True},
                    ],
                },
            }],
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(self._webhook_url, json=card)
        except httpx.TimeoutException as exc:
            raise ChannelConnectionError(f"Teams webhook timeout: {exc}") from exc
        except httpx.RequestError as exc:
            raise ChannelConnectionError(f"Teams webhook network error: {exc}") from exc

        if response.status_code == 429:
            raise ChannelRateLimitError("Teams webhook 429 — rate limited")
        if response.status_code >= 300:
            raise ChannelDeliveryError(
                f"Teams webhook delivery failed: HTTP {response.status_code}"
            )

        return DeliveryResult(success=True, message_ts=None)

    async def test_connection(self) -> ConnectionTestResult:
        """Send a test ping message to the webhook. NEVER raises."""
        start = time.monotonic()
        try:
            if self._webhook_url is None:
                return ConnectionTestResult(success=False, error_detail="Not connected")
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.post(
                    self._webhook_url,
                    json={"type": "message", "text": "mailwise health check"},
                )
            latency_ms = int((time.monotonic() - start) * 1000)
            return ConnectionTestResult(success=response.status_code < 300,
                                        latency_ms=latency_ms)
        except Exception as exc:
            return ConnectionTestResult(success=False, error_detail=str(exc))

    async def get_available_destinations(self) -> list[Destination]:
        """Webhooks target a single channel — return that channel as destination."""
        self._ensure_connected()
        return [Destination(id="webhook", name="Teams Webhook Channel", type="channel")]
```

### Step 2: Register in config

```python
channel_provider: str = Field(default="slack")  # "slack" | "teams"
teams_webhook_url: str = Field(default="")
```

### Step 3: Wire into DI factory

In `src/api/deps.py`, update `get_routing_service()`:

```python
from src.adapters.channel.teams import TeamsAdapter

if settings.channel_provider == "teams" and settings.teams_webhook_url:
    teams = TeamsAdapter()
    await teams.connect(ChannelCredentials(bot_token=settings.teams_webhook_url))
    channel_adapters["teams"] = teams
elif settings.slack_bot_token:
    slack = SlackAdapter()
    await slack.connect(ChannelCredentials(bot_token=settings.slack_bot_token))
    channel_adapters["slack"] = slack
```

### Step 4: Add to .env.example

```bash
# --- Channel Provider ---
# Default: slack. Options: slack | teams
CHANNEL_PROVIDER=slack

# Microsoft Teams (Incoming Webhook) — required if CHANNEL_PROVIDER=teams
TEAMS_WEBHOOK_URL=
```

### Step 5: Write integration test

```python
# tests/integration/test_teams_adapter.py
import pytest
from src.adapters.channel.teams import TeamsAdapter
from src.adapters.channel.schemas import ChannelCredentials

@pytest.mark.asyncio
@pytest.mark.integration
async def test_teams_connect_rejects_non_https() -> None:
    adapter = TeamsAdapter()
    with pytest.raises(ValueError, match="https://"):
        await adapter.connect(ChannelCredentials(bot_token="http://invalid"))

@pytest.mark.asyncio
@pytest.mark.integration
async def test_teams_test_connection_never_raises() -> None:
    adapter = TeamsAdapter()
    result = await adapter.test_connection()
    assert result.success is False
    assert result.error_detail is not None
```

---

## CRM Adapter — adding Salesforce

**ABC:** `src/adapters/crm/base.py`
**Schemas:** `src/adapters/crm/schemas.py`
**Exceptions:** `src/adapters/crm/exceptions.py`

### Methods to implement

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

Note: `update_field()` silences `FieldNotFoundError` (HTTP 400 + PROPERTY_DOESNT_EXIST) — this is a deliberate CRM sync contract per Sec 6.4.

### Step 1: Implement the ABC

Create `src/adapters/crm/salesforce.py`:

```python
"""SalesforceAdapter — CRMAdapter for Salesforce REST API.

Invariants: OAuth2 session token loaded via ``connect()``. Instance URL
    and session ID are required for all operations.
  Guarantees: All returned values are typed schemas. Salesforce API
    responses never leak past this adapter.
  Errors raised: Typed ``CRMAdapterError`` subclasses (see exceptions.py).
  Errors silenced: ``test_connection()`` silences all errors.
    ``update_field()`` silences ``FieldNotFoundError`` per Sec 6.4.
  External state: Salesforce REST API v56.0.
"""

from __future__ import annotations

import time
from datetime import datetime

import httpx
import structlog

from src.adapters.crm.base import CRMAdapter
from src.adapters.crm.exceptions import (
    ContactNotFoundError,
    CRMAuthError,
    CRMConnectionError,
    CRMRateLimitError,
    DuplicateContactError,
    FieldNotFoundError,
)
from src.adapters.crm.schemas import (
    ActivityData,
    ActivityId,
    ConnectionStatus,
    ConnectionTestResult,
    Contact,
    CreateContactData,
    CreateLeadData,
    CRMCredentials,
    LeadId,
)

logger = structlog.get_logger(__name__)

_API_VERSION = "v56.0"


class SalesforceAdapter(CRMAdapter):
    """Salesforce CRM adapter using the REST API."""

    def __init__(self) -> None:
        self._session_id: str | None = None
        self._instance_url: str | None = None

    def _ensure_connected(self) -> None:
        if self._session_id is None:
            raise CRMAuthError("SalesforceAdapter.connect() has not been called")

    def _base_url(self) -> str:
        assert self._instance_url is not None
        return f"{self._instance_url}/services/data/{_API_VERSION}"

    def _headers(self) -> dict[str, str]:
        assert self._session_id is not None
        return {"Authorization": f"Bearer {self._session_id}",
                "Content-Type": "application/json"}

    async def connect(self, credentials: CRMCredentials) -> ConnectionStatus:
        """Authenticate via Salesforce OAuth2 username-password flow.

        Preconditions:
          - ``credentials.access_token`` contains the session ID (or OAuth token).
          - Set ``instance_url`` as the base Salesforce org URL.

        Guarantees:
          - On success, adapter is ready for subsequent operations.

        Errors raised:
          - ``ValueError`` if ``access_token`` is empty.
          - ``CRMAuthError`` on HTTP 401.
          - ``CRMConnectionError`` on network failure.

        Errors silenced: None.
        """
        if not credentials.access_token:
            raise ValueError("credentials.access_token is required")

        # For Salesforce, access_token is the session ID
        # instance_url is stored in a separate credential field or env var
        self._session_id = credentials.access_token
        # Extract instance URL from metadata field if present
        self._instance_url = getattr(credentials, "instance_url",
                                     "https://your-org.salesforce.com")

        # Verify by fetching org limits
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self._base_url()}/limits",
                    headers=self._headers(),
                )
        except httpx.RequestError as exc:
            raise CRMConnectionError(f"Salesforce connect network error: {exc}") from exc

        if response.status_code == 401:
            raise CRMAuthError("Salesforce 401 — invalid session ID")
        return ConnectionStatus(connected=True)

    async def lookup_contact(self, email: str) -> Contact | None:
        """Query Contact by email via SOQL.

        Preconditions:
          - ``email`` is non-empty and contains '@'.
          - Adapter is connected.

        Guarantees:
          - Returns ``Contact`` if found, ``None`` otherwise.
          - On multiple matches, returns the most recently modified.

        Errors raised:
          - ``ValueError`` if ``email`` is empty or missing '@'.
          - ``CRMAuthError`` on 401.
          - ``CRMRateLimitError`` on 429.
          - ``CRMConnectionError`` on network failure.

        Errors silenced:
          - Multiple matches: uses the most recently modified, logs warning.
        """
        self._ensure_connected()

        if not email or "@" not in email:
            raise ValueError(f"Invalid email: {email!r}")

        soql = (
            f"SELECT Id,Name,Email,LastModifiedDate FROM Contact "
            f"WHERE Email='{email}' ORDER BY LastModifiedDate DESC LIMIT 5"
        )
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{self._base_url()}/query",
                    params={"q": soql},
                    headers=self._headers(),
                )
        except httpx.RequestError as exc:
            raise CRMConnectionError(f"lookup_contact network error: {exc}") from exc

        if response.status_code == 401:
            raise CRMAuthError("Salesforce 401")
        if response.status_code == 429:
            raise CRMRateLimitError("Salesforce 429")

        records = response.json().get("records", [])
        if not records:
            return None
        if len(records) > 1:
            logger.warning("salesforce.lookup_contact.ambiguous",
                           email=email, contact_count=len(records))
        r = records[0]
        return Contact(id=r["Id"], email=r["Email"], name=r["Name"])

    async def create_contact(self, data: CreateContactData) -> Contact:
        """Create a new Contact in Salesforce.

        Preconditions:
          - ``data.email`` is non-empty and contains '@'.
          - Adapter is connected.

        Errors raised:
          - ``DuplicateContactError`` if email already exists (HTTP 400 + DUPLICATE_VALUE).
          - ``CRMAuthError``, ``CRMRateLimitError``, ``CRMConnectionError``.
        """
        self._ensure_connected()

        if not data.email or "@" not in data.email:
            raise ValueError(f"Invalid email: {data.email!r}")

        name_parts = (data.name or data.email).split(" ", 1)
        payload = {
            "Email": data.email,
            "FirstName": name_parts[0],
            "LastName": name_parts[1] if len(name_parts) > 1 else "-",
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{self._base_url()}/sobjects/Contact",
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.RequestError as exc:
            raise CRMConnectionError(f"create_contact network error: {exc}") from exc

        if response.status_code == 401:
            raise CRMAuthError("Salesforce 401")
        if response.status_code == 429:
            raise CRMRateLimitError("Salesforce 429")
        if response.status_code == 400:
            errors = response.json()
            if any(e.get("errorCode") == "DUPLICATE_VALUE" for e in errors):
                raise DuplicateContactError(f"Contact already exists: {data.email}")
            raise CRMConnectionError(f"Salesforce 400: {errors}")

        contact_id = response.json()["id"]
        return Contact(id=contact_id, email=data.email, name=data.name or "")

    async def log_activity(
        self, contact_id: str, activity: ActivityData
    ) -> ActivityId:
        """Create a Task linked to the Contact as an email activity log."""
        self._ensure_connected()

        if not contact_id:
            raise ValueError("contact_id is required")

        payload = {
            "Subject": activity.subject,
            "WhoId": contact_id,
            "Description": activity.snippet,
            "ActivityDate": activity.timestamp.strftime("%Y-%m-%d"),
            "Status": "Completed",
            "Type": "Email",
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{self._base_url()}/sobjects/Task",
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.RequestError as exc:
            raise CRMConnectionError(f"log_activity network error: {exc}") from exc

        if response.status_code == 404:
            raise ContactNotFoundError(f"Contact {contact_id} not found")
        if response.status_code == 401:
            raise CRMAuthError("Salesforce 401")

        return ActivityId(id=response.json()["id"])

    async def create_lead(self, data: CreateLeadData) -> LeadId:
        """Create an Opportunity linked to the Contact."""
        self._ensure_connected()

        if not data.contact_id or not data.summary:
            raise ValueError("contact_id and summary are required")

        payload = {
            "Name": data.summary[:120],
            "LeadSource": data.source,
            "StageName": "Prospecting",
            "CloseDate": datetime.now().strftime("%Y-%m-%d"),
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{self._base_url()}/sobjects/Opportunity",
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.RequestError as exc:
            raise CRMConnectionError(f"create_lead network error: {exc}") from exc

        if response.status_code == 404:
            raise ContactNotFoundError(f"Contact {data.contact_id} not found")

        return LeadId(id=response.json()["id"])

    async def update_field(
        self, contact_id: str, field: str, value: str
    ) -> None:
        """Update a Contact property. Silences FieldNotFoundError per Sec 6.4."""
        self._ensure_connected()

        if not contact_id or not field:
            raise ValueError("contact_id and field are required")

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.patch(
                    f"{self._base_url()}/sobjects/Contact/{contact_id}",
                    headers=self._headers(),
                    json={field: value},
                )
        except httpx.RequestError as exc:
            raise CRMConnectionError(f"update_field network error: {exc}") from exc

        if response.status_code == 404:
            raise ContactNotFoundError(f"Contact {contact_id} not found")
        if response.status_code == 400:
            errors = response.json() if response.content else []
            if any(e.get("errorCode") == "INVALID_FIELD" for e in errors):
                logger.warning("salesforce.update_field.field_not_found",
                               field=field, contact_id=contact_id)
                raise FieldNotFoundError(f"Field {field!r} does not exist")
            raise CRMConnectionError(f"Salesforce 400: {errors}")
        # FieldNotFoundError is caught and silenced by the calling service
        # (CRMSyncService._sync_contact_fields) per Sec 6.4 contract

    async def test_connection(self) -> ConnectionTestResult:
        """Query org limits. NEVER raises."""
        start = time.monotonic()
        try:
            if self._session_id is None:
                return ConnectionTestResult(success=False,
                                            error_detail="Not connected")
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(
                    f"{self._base_url()}/limits",
                    headers=self._headers(),
                )
            latency_ms = int((time.monotonic() - start) * 1000)
            return ConnectionTestResult(success=response.status_code == 200,
                                        latency_ms=latency_ms)
        except Exception as exc:
            return ConnectionTestResult(success=False, error_detail=str(exc))
```

### Step 2: Register in config

```python
crm_provider: str = Field(default="hubspot")  # "hubspot" | "salesforce"
salesforce_session_id: str = Field(default="")
salesforce_instance_url: str = Field(default="")
```

### Step 3: Wire into DI factory

In `src/services/crm_sync.py` (or the CRM service factory):

```python
from src.adapters.crm.hubspot import HubSpotAdapter
from src.adapters.crm.salesforce import SalesforceAdapter

def get_crm_adapter(settings: Settings) -> CRMAdapter:
    if settings.crm_provider == "salesforce":
        return SalesforceAdapter()
    return HubSpotAdapter()
```

### Step 4: Add to .env.example

```bash
# --- CRM Provider ---
# Default: hubspot. Options: hubspot | salesforce
CRM_PROVIDER=hubspot

# Salesforce — required if CRM_PROVIDER=salesforce
SALESFORCE_SESSION_ID=
SALESFORCE_INSTANCE_URL=https://your-org.salesforce.com
```

### Step 5: Write integration test

```python
# tests/integration/test_salesforce_adapter.py
import pytest
from src.adapters.crm.salesforce import SalesforceAdapter
from src.adapters.crm.schemas import CRMCredentials

@pytest.mark.asyncio
@pytest.mark.integration
async def test_salesforce_connect_rejects_empty_token() -> None:
    adapter = SalesforceAdapter()
    with pytest.raises(ValueError, match="access_token"):
        await adapter.connect(CRMCredentials(access_token=""))

@pytest.mark.asyncio
@pytest.mark.integration
async def test_salesforce_test_connection_never_raises() -> None:
    adapter = SalesforceAdapter()
    result = await adapter.test_connection()
    assert result.success is False
```

---

## LLM Adapter — adding Ollama

**ABC:** `src/adapters/llm/base.py`
**Schemas:** `src/adapters/llm/schemas.py`
**Exceptions:** `src/adapters/llm/exceptions.py`

### Methods to implement

```python
class LLMAdapter(abc.ABC):
    async def classify(self, prompt: str, system_prompt: str,
                       options: ClassifyOptions) -> ClassificationResult: ...
    async def generate_draft(self, prompt: str, system_prompt: str,
                             options: DraftOptions) -> DraftText: ...
    async def test_connection(self) -> ConnectionTestResult: ...
```

**Critical contract:** `classify()` MUST apply a fallback on parse failure — return `ClassificationResult(fallback_applied=True, confidence="low")` rather than raising. `generate_draft()` has NO fallback — errors propagate.

The current `LiteLLMAdapter` already supports Ollama via `LLM_BASE_URL`. This section shows how to implement a **direct Ollama adapter** without LiteLLM as an alternative.

### Step 1: Implement the ABC

Create `src/adapters/llm/ollama.py`:

```python
"""OllamaAdapter — LLMAdapter for local Ollama inference.

Invariants: ``LLMConfig`` loaded before any operation except
    ``test_connection()``. Ollama server reachable at ``base_url``.
  Guarantees: All returned values are typed schemas. Raw Ollama JSON
    never leaks past this adapter. ``classify()`` always returns a
    ``ClassificationResult`` — fallback applied on parse failure.
  Errors raised: Typed ``LLMAdapterError`` subclasses (see exceptions.py).
  Errors silenced: ``test_connection()`` silences all errors.
    ``classify()`` silences ``OutputParseError`` (fallback applied).
  External state: Ollama server REST API (typically localhost:11434).
"""

from __future__ import annotations

import json
import re
import time

import httpx
import structlog

from src.adapters.llm.base import LLMAdapter
from src.adapters.llm.exceptions import (
    LLMConnectionError,
    LLMRateLimitError,
    LLMTimeoutError,
    OutputParseError,
)
from src.adapters.llm.schemas import (
    ClassificationResult,
    ClassifyOptions,
    ConnectionTestResult,
    DraftOptions,
    DraftText,
)

logger = structlog.get_logger(__name__)

_FALLBACK_RESULT = ClassificationResult(
    action="inform",
    type="notification",
    confidence="low",
    category_slug=None,
    reasoning="LLM output parse failed — fallback applied",
    raw_llm_output="",
    fallback_applied=True,
)


class OllamaAdapter(LLMAdapter):
    """Direct Ollama adapter for local inference (no LiteLLM intermediary)."""

    def __init__(self, base_url: str = "http://localhost:11434",
                 model: str = "llama3") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def classify(
        self,
        prompt: str,
        system_prompt: str,
        options: ClassifyOptions,
    ) -> ClassificationResult:
        """Classify email via Ollama. Returns fallback on parse failure.

        Preconditions:
          - ``prompt`` is a non-empty sanitized email string.
          - ``system_prompt`` includes category definitions.
          - ``options.allowed_actions`` and ``options.allowed_types`` non-empty.

        Guarantees:
          - Always returns ``ClassificationResult`` (never raises on parse failure).
          - ``fallback_applied=True`` when the model output cannot be parsed.
          - ``raw_llm_output`` is always preserved for debugging.

        Errors raised:
          - ``ValueError`` if ``prompt`` or ``system_prompt`` is empty.
          - ``LLMConnectionError`` on network failure.
          - ``LLMTimeoutError`` on timeout.

        Errors silenced:
          - ``OutputParseError`` — fallback applied, logged with raw output.
        """
        if not prompt:
            raise ValueError("prompt is required")
        if not system_prompt:
            raise ValueError("system_prompt is required")
        if not options.allowed_actions:
            raise ValueError("options.allowed_actions must be non-empty")

        raw_output = await self._call_ollama(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=options.temperature,
            max_tokens=500,
        )

        try:
            return self._parse_classification(raw_output, options)
        except OutputParseError:
            logger.warning("ollama.classify.parse_failed",
                           raw_output=raw_output[:200])
            result = _FALLBACK_RESULT
            result.raw_llm_output = raw_output
            return result

    async def generate_draft(
        self,
        prompt: str,
        system_prompt: str,
        options: DraftOptions,
    ) -> DraftText:
        """Generate a draft email. Errors propagate — no fallback.

        Preconditions:
          - ``prompt`` and ``system_prompt`` are non-empty.

        Guarantees:
          - Returns ``DraftText`` with non-empty ``content``.

        Errors raised:
          - ``ValueError`` if ``prompt`` or ``system_prompt`` is empty.
          - ``LLMConnectionError``, ``LLMTimeoutError``.

        Errors silenced: None.
        """
        if not prompt:
            raise ValueError("prompt is required")
        if not system_prompt:
            raise ValueError("system_prompt is required")

        content = await self._call_ollama(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=options.temperature,
            max_tokens=2000,
        )
        return DraftText(content=content, model_used=self._model)

    async def _call_ollama(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Make a single call to the Ollama /api/chat endpoint."""
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": temperature, "num_predict": max_tokens},
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self._base_url}/api/chat", json=payload
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Ollama timeout: {exc}") from exc
        except httpx.RequestError as exc:
            raise LLMConnectionError(f"Ollama network error: {exc}") from exc

        if response.status_code == 429:
            raise LLMRateLimitError("Ollama 429")
        if response.status_code >= 500:
            raise LLMConnectionError(f"Ollama server error: {response.status_code}")

        return response.json()["message"]["content"]

    def _parse_classification(
        self, raw: str, options: ClassifyOptions
    ) -> ClassificationResult:
        """Extract JSON classification block from LLM output.

        Raises ``OutputParseError`` if parsing fails — caller applies fallback.
        """
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise OutputParseError("No JSON object found in LLM output")
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as exc:
            raise OutputParseError(f"JSON parse failed: {exc}") from exc

        action = data.get("action", "")
        if action not in options.allowed_actions:
            raise OutputParseError(f"action {action!r} not in allowed_actions")

        return ClassificationResult(
            action=action,
            type=data.get("type", "notification"),
            confidence=data.get("confidence", "low"),
            category_slug=data.get("category_slug"),
            reasoning=data.get("reasoning", ""),
            raw_llm_output=raw,
            fallback_applied=False,
        )

    async def test_connection(self) -> ConnectionTestResult:
        """Ping Ollama /api/tags. NEVER raises."""
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self._base_url}/api/tags")
            latency_ms = int((time.monotonic() - start) * 1000)
            return ConnectionTestResult(
                success=response.status_code == 200,
                latency_ms=latency_ms,
                error_detail=None if response.status_code == 200 else
                             f"HTTP {response.status_code}",
            )
        except Exception as exc:
            return ConnectionTestResult(success=False, error_detail=str(exc))
```

### Step 2: Register in config

The existing `LLM_BASE_URL` setting already routes LiteLLM to Ollama. To use the direct adapter instead:

```python
llm_provider: str = Field(default="litellm")  # "litellm" | "ollama"
```

### Step 3: Wire into DI factory

In whichever service creates the LLM adapter:

```python
from src.adapters.llm.litellm import LiteLLMAdapter
from src.adapters.llm.ollama import OllamaAdapter

def get_llm_adapter(settings: Settings) -> LLMAdapter:
    if settings.llm_provider == "ollama":
        return OllamaAdapter(
            base_url=settings.llm_base_url or "http://localhost:11434",
            model=settings.llm_model_classify,
        )
    return LiteLLMAdapter(settings=settings)
```

### Step 4: Add to .env.example

```bash
# --- LLM Provider ---
# Default: litellm. Options: litellm | ollama
# Note: litellm already supports Ollama via LLM_BASE_URL.
# Use ollama for direct adapter (no LiteLLM dependency).
LLM_PROVIDER=litellm

# Ollama (direct) — required if LLM_PROVIDER=ollama
# LLM_BASE_URL already serves as the Ollama base URL.
# LLM_MODEL_CLASSIFY and LLM_MODEL_DRAFT specify the Ollama model name.
```

### Step 5: Write integration test

```python
# tests/integration/test_ollama_adapter.py
import pytest
from unittest.mock import AsyncMock, patch

from src.adapters.llm.ollama import OllamaAdapter
from src.adapters.llm.schemas import ClassifyOptions, DraftOptions

@pytest.mark.asyncio
async def test_ollama_classify_returns_fallback_on_bad_json() -> None:
    adapter = OllamaAdapter(base_url="http://localhost:11434", model="llama3")
    with patch.object(adapter, "_call_ollama", new=AsyncMock(return_value="not json")):
        result = await adapter.classify(
            prompt="Test email content",
            system_prompt="Classify as inquiry or complaint.",
            options=ClassifyOptions(
                allowed_actions=["route", "inform"],
                allowed_types=["inquiry", "complaint"],
                temperature=0.1,
            ),
        )
    assert result.fallback_applied is True
    assert result.confidence == "low"

@pytest.mark.asyncio
async def test_ollama_test_connection_never_raises() -> None:
    adapter = OllamaAdapter(base_url="http://nonexistent:11434")
    result = await adapter.test_connection()
    assert result.success is False
    assert result.error_detail is not None
```

---

## Common Patterns

### The `_ensure_connected()` idiom

Every adapter that requires `connect()` before operations uses this guard:

```python
def _ensure_connected(self) -> None:
    if self._client is None:
        raise SomeDomainAuthError("Adapter.connect() has not been called")
```

Follow this with `assert self._client is not None` after the call to satisfy mypy narrowing:

```python
def some_method(self) -> ...:
    self._ensure_connected()
    assert self._client is not None  # narrows type from X | None to X
    # now mypy knows self._client is not None
    return self._client.do_something()
```

### `test_connection()` contract

Every adapter's `test_connection()` follows this contract without exception:

- NEVER raises
- ALL errors are caught and returned in the result struct
- Measures `latency_ms` via `time.monotonic()`
- Returns a typed result with `success: bool` and an optional `error_detail` field

### Exception hierarchy

Each family defines its own exception tree in `exceptions.py`. Map provider HTTP status codes to domain exceptions consistently:

| HTTP Status | Domain Exception |
|-------------|-----------------|
| 401 | `*AuthError` |
| 404 | `*NotFoundError` |
| 409 | `Duplicate*Error` |
| 429 | `*RateLimitError` |
| 5xx | `*ConnectionError` |
| Network timeout | `*ConnectionError` or `*TimeoutError` |

### Sync SDK wrapping (for Celery tasks)

If the provider SDK is synchronous (like `hubspot-api-client`), wrap calls with `asyncio.to_thread()`:

```python
result = await asyncio.to_thread(sdk_client.sync_method, arg1, arg2)
```

In tests, monkeypatch `asyncio.to_thread` to avoid real thread creation:

```python
async def _sync_to_thread(func, /, *args, **kwargs):
    return func(*args, **kwargs)

monkeypatch.setattr("asyncio.to_thread", _sync_to_thread)
```
