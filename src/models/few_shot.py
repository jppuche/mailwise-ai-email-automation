"""Few-shot example model for classification prompt engineering.

Admin-curated examples that improve LLM classification accuracy.
Used by ClassificationService to build few-shot prompts.

action_slug and type_slug are string references (not FK UUIDs) for flexibility —
validated at service layer against active categories. This matches how
FeedbackExample dataclass works in src/services/schemas/classification.py.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class FewShotExample(Base, TimestampMixin):
    """Admin-curated few-shot example for the classification prompt."""

    __tablename__ = "few_shot_examples"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_snippet: Mapped[str] = mapped_column(sa.Text, nullable=False)
    action_slug: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    type_slug: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    rationale: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
