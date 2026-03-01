"""Typed result dataclasses for pipeline tasks.

Each task produces a frozen dataclass result stored in DB — never via
Celery result backend (``AsyncResult.get()`` returns ``Any`` — D3).

tighten-types D1: No ``Any`` fields. All fields fully typed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class IngestResult:
    """Result of ``ingest_task``: batch ingestion summary."""

    account_id: str
    emails_fetched: int
    emails_skipped: int
    emails_failed: int


@dataclass(frozen=True)
class ClassifyResult:
    """Result of ``classify_task``: single email classification outcome."""

    email_id: uuid.UUID
    success: bool
    action: str | None = None
    type: str | None = None
    confidence: str | None = None


@dataclass(frozen=True)
class RouteResult:
    """Result of ``route_task``: routing dispatch summary."""

    email_id: uuid.UUID
    actions_dispatched: int
    actions_failed: int


@dataclass(frozen=True)
class CRMSyncTaskResult:
    """Result of ``crm_sync_task``.

    Named ``CRMSyncTaskResult`` to avoid collision with service-level
    ``CRMSyncResult`` in ``src.services.schemas.crm_sync``.
    """

    email_id: uuid.UUID
    contact_id: str | None = None
    activity_id: str | None = None
    overall_success: bool = False


@dataclass(frozen=True)
class DraftTaskResult:
    """Result of ``draft_task``.

    Named ``DraftTaskResult`` to avoid collision with service-level
    ``DraftResult`` in ``src.services.schemas.draft``.
    """

    email_id: uuid.UUID
    draft_id: uuid.UUID | None = None
    status: str = "pending"
