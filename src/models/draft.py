"""Draft model.

A Draft is an LLM-generated reply draft for an email that requires a response.
Drafts go through a review queue (PENDING -> APPROVED/REJECTED) before being
pushed to the email provider.

Gmail push failure leaves the email in DRAFT_GENERATED state
(not DRAFT_FAILED). The draft row persists. pushed_to_provider records whether
the push succeeded.
"""

import datetime
import uuid
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, _enum_values


class DraftStatus(StrEnum):
    """Review status of a draft in the reviewer queue."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Draft(Base, TimestampMixin):
    """LLM-generated reply draft awaiting reviewer action.

    reviewer_id is SET NULL if the reviewer user is deleted — the draft record
    and its review decision are preserved for audit purposes.
    """

    __tablename__ = "drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[DraftStatus] = mapped_column(
        sa.Enum(
            DraftStatus,
            name="draftstatus",
            create_type=True,
            values_callable=_enum_values,
        ),
        nullable=False,
        default=DraftStatus.PENDING,
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    pushed_to_provider: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
