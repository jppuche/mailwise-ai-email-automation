"""Classification feedback model.

Reviewers can correct misclassified emails via the review queue.
Each correction is stored as a ClassificationFeedback row.

This feedback is used by the Tier 2 feedback loop for prompt improvement
and fine-tuning. It preserves both the original and corrected classifications
for analysis.
"""

import datetime
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class ClassificationFeedback(Base, TimestampMixin):
    """Reviewer correction of an incorrect email classification.

    Stores the original classification (from ClassificationResult) and the
    reviewer's correction. corrected_by references the User who made the
    correction — preserved as NULL if the user is later deleted.

    All FK references to categories use no ondelete rule (default RESTRICT)
    to prevent accidental category deletion if feedback exists.
    """

    __tablename__ = "classification_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_action_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("action_categories.id"),
        nullable=False,
    )
    original_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("type_categories.id"),
        nullable=False,
    )
    corrected_action_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("action_categories.id"),
        nullable=False,
    )
    corrected_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("type_categories.id"),
        nullable=False,
    )
    corrected_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id"),
        nullable=False,
    )
    corrected_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
