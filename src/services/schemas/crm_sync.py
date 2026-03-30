"""CRM sync service data contracts.

No ``dict[str, Any]`` at boundaries.
``field_updates: dict[str, str]`` is a documented exception — both key
and value are ``str``, not ``Any``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CRMSyncConfig(BaseModel):
    """All values sourced from Settings (env vars)."""

    auto_create_contacts: bool
    activity_snippet_length: int
    retry_max: int
    backoff_base_seconds: int


class CRMSyncRequest(BaseModel):
    """Input to CRMSyncService.sync().

    Privacy (Sec 6.5): No body_plain or body_html field.
    ``snippet`` is pre-truncated by the caller.
    """

    email_id: uuid.UUID
    sender_email: str
    sender_name: str | None = None
    subject: str
    snippet: str
    classification_action: str
    classification_type: str
    received_at: datetime
    create_lead: bool = False
    field_updates: dict[str, str] = {}


class CRMOperationStatus(BaseModel):
    """Outcome of a single CRM operation."""

    operation: Literal[
        "contact_lookup",
        "contact_create",
        "activity_log",
        "lead_create",
        "field_update",
    ]
    success: bool
    crm_id: str | None = None
    skipped: bool = False
    error: str | None = None


class CRMSyncResult(BaseModel):
    """Complete result of one CRM sync attempt."""

    email_id: uuid.UUID
    contact_id: str | None = None
    activity_id: str | None = None
    lead_id: str | None = None
    operations: list[CRMOperationStatus]
    overall_success: bool
    paused_for_auth: bool = False
