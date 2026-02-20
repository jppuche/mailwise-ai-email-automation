"""CRM sync record model.

Records the outcome of each CRM synchronization attempt for an email.
One CRMSyncRecord per email — created after the CRM sync task completes
(successfully or not).

contact_id, activity_id, and lead_id are provider-assigned IDs from HubSpot.
They are nullable because sync may fail or be skipped before these IDs are assigned.
"""

import datetime
import uuid
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class CRMSyncStatus(StrEnum):
    """Outcome status of a CRM synchronization attempt."""

    SYNCED = "synced"
    FAILED = "failed"
    SKIPPED = "skipped"


class CRMSyncRecord(Base, TimestampMixin):
    """Audit record of CRM sync outcome for an email.

    CRMAuthError (non-retryable) results in status=FAILED with no retry.
    Idempotency is checked via the DB record, never by querying the CRM API.
    """

    __tablename__ = "crm_sync_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    activity_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    lead_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    status: Mapped[CRMSyncStatus] = mapped_column(
        sa.Enum(CRMSyncStatus, name="crmsyncstatus", create_type=True),
        nullable=False,
    )
    synced_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
