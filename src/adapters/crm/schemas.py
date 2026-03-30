"""Adapter-boundary data contracts for CRM operations.

No ``dict[str, Any]`` in any public type.
"""

from __future__ import annotations

from datetime import datetime
from typing import NewType

from pydantic import BaseModel, field_validator

# Semantic type aliases — not bare str
ActivityId = NewType("ActivityId", str)
LeadId = NewType("LeadId", str)


class CRMCredentials(BaseModel):
    """Credentials for connecting to the CRM adapter."""

    access_token: str  # HubSpot Private App Token


class ConnectionStatus(BaseModel):
    """Result of a connect() call."""

    connected: bool
    portal_id: str | None = None
    account_name: str | None = None
    error: str | None = None


class ConnectionTestResult(BaseModel):
    """Result of a test_connection() health check."""

    success: bool
    portal_id: str | None = None
    latency_ms: int
    error_detail: str | None = None


class Contact(BaseModel):
    """Contact in the CRM. Never exposes HubSpot SDK objects."""

    id: str  # Numeric HubSpot ID as str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreateContactData(BaseModel):
    """Data for creating a new contact."""

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
    """Data for logging an activity in the CRM (email received).

    ``snippet`` must be pre-truncated by the calling service to
    ``HUBSPOT_ACTIVITY_SNIPPET_LENGTH``. No ``body`` or ``body_plain``
    field — PII policy (Sec 6.5).
    """

    subject: str
    timestamp: datetime  # timezone-aware
    classification_action: str
    classification_type: str
    snippet: str  # pre-truncated by calling service
    email_id: str
    dashboard_link: str | None = None


class CreateLeadData(BaseModel):
    """Data for creating a lead (deal) in the CRM."""

    contact_id: str
    summary: str
    source: str
    lead_status: str = "NEW"
