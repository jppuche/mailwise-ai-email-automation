"""Classification result model.

NOTE on naming: This is the DB persistence model. Do NOT confuse with
the adapter-layer dataclass ClassificationResult in src/adapters/llm/types.py
(Block 04). The adapter dataclass transports the result from the LLM adapter
to the service layer. This model persists it to the database.

If you need to import both, alias the adapter class:
    from src.adapters.llm.types import ClassificationResult as AdapterClassificationResult
    from src.models.classification import ClassificationResult
"""

import datetime
import uuid
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, _enum_values


class ClassificationConfidence(StrEnum):
    """Confidence level of the LLM classification.

    HIGH: LLM returned a classification above the confidence threshold.
    LOW: LLM returned a classification below the threshold — review queue candidate.
    """

    HIGH = "high"
    LOW = "low"


class ClassificationResult(Base, TimestampMixin):
    """Persisted LLM classification result for an email.

    FK constraints to action_categories and type_categories enforce that only
    valid DB-backed categories can be stored. This prevents LLM hallucinations
    from corrupting the classification record.

    raw_llm_output is intentionally typed as dict (not a TypedDict) — it stores
    the raw, unparsed response from the LLM provider before extraction. Shape
    varies by provider. The adapter layer validates and extracts typed fields
    before creating this record.
    """

    __tablename__ = "classification_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("action_categories.id"),
        nullable=False,
    )
    type_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("type_categories.id"),
        nullable=False,
    )
    confidence: Mapped[ClassificationConfidence] = mapped_column(
        sa.Enum(
            ClassificationConfidence,
            name="classificationconfidence",
            create_type=True,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    raw_llm_output: Mapped[dict] = mapped_column(JSONB, nullable=False)  # type: ignore[type-arg]
    fallback_applied: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    classified_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
