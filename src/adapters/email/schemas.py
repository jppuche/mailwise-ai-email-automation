"""Adapter-boundary data contracts for email operations.

These types define the data that crosses the adapter boundary. They are
independent of the ORM models in ``src.models.email`` — the Ingestion
Service (Block 07) is responsible for mapping between the two.

tighten-types D1: No ``dict[str, Any]`` in any public type.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NewType, TypedDict

from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# NewType — branded str for draft identifiers
# ---------------------------------------------------------------------------

DraftId = NewType("DraftId", str)

# ---------------------------------------------------------------------------
# TypedDicts — lightweight nested structures for JSONB-compatible fields
# ---------------------------------------------------------------------------


class RecipientData(TypedDict):
    """A single email recipient.

    The adapter produces separate ``to_addresses`` and ``cc_addresses`` lists,
    so there is no ``type`` discriminator here (unlike the ORM TypedDict which
    carries ``type: "to" | "cc" | "bcc"``).
    """

    email: str
    name: str | None


class AttachmentData(TypedDict):
    """Metadata for a single attachment (content not downloaded)."""

    filename: str
    mime_type: str
    size_bytes: int
    attachment_id: str


# ---------------------------------------------------------------------------
# Pydantic BaseModels — fully typed boundary objects
# ---------------------------------------------------------------------------


class EmailCredentials(BaseModel):
    """OAuth2 credentials required to connect to an email provider."""

    client_id: str
    client_secret: str
    token: str
    refresh_token: str
    token_uri: str = "https://oauth2.googleapis.com/token"
    scopes: list[str] = []


class ConnectionStatus(BaseModel):
    """Result of a successful ``connect()`` call."""

    connected: bool
    account: str | None = None
    scopes: list[str] = []


class ConnectionTestResult(BaseModel):
    """Result of ``test_connection()`` — never raises, always returns this."""

    connected: bool
    account: str | None = None
    scopes: list[str] = []
    error: str | None = None


class Label(BaseModel):
    """An email label / folder from the provider."""

    id: str
    name: str
    type: str  # "system" | "user"


class EmailMessage(BaseModel):
    """A single email message as returned by the adapter.

    ``received_at`` is always timezone-aware UTC. A field validator coerces
    naive datetimes to UTC if they arrive without timezone info.
    """

    id: str
    gmail_message_id: str
    thread_id: str | None = None
    subject: str = ""
    from_address: str
    to_addresses: list[RecipientData] = []
    cc_addresses: list[RecipientData] = []
    body_plain: str | None = None
    body_html: str | None = None
    snippet: str | None = None
    received_at: datetime
    attachments: list[AttachmentData] = []
    raw_headers: dict[str, str] = {}
    provider_labels: list[str] = []

    @field_validator("received_at", mode="before")
    @classmethod
    def _ensure_timezone_aware(cls, v: datetime) -> datetime:
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v
