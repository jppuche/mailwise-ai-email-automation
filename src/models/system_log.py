"""System log model for structured audit logging.

Stores pipeline events for the admin log viewer. email_id is NOT a FK —
logs persist even if the email is deleted. context is dict[str, str]
(not Any) per PII policy: only IDs and slugs, never email content.
"""

from __future__ import annotations

import datetime
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class SystemLog(Base, TimestampMixin):
    """Structured audit log entry for pipeline observability."""

    __tablename__ = "system_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, index=True
    )
    level: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    source: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    message: Mapped[str] = mapped_column(sa.Text, nullable=False)
    email_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    context: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
