"""Classification category models.

Categories are stored in the DB — not as Python enums — to allow runtime
configurability without redeployment. Classification results FK to category
rows, making it impossible for an LLM hallucination to write a free-form
string that bypasses validation.

Two category layers:
  - ActionCategory (Layer 1): What action does the email require?
    e.g. urgent, reply_needed, informational, unknown (fallback)
  - TypeCategory (Layer 2): What type of email is it?
    e.g. customer_support, sales_inquiry, billing, spam_automated, other (fallback)

Seed data for both tables is in alembic/versions/001_initial_schema.py.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class ActionCategory(Base, TimestampMixin):
    """Layer 1 classification: what action does the email require?

    e.g. 'urgent', 'reply_needed', 'informational', 'unknown' (fallback).
    The fallback category (is_fallback=True) is used when the LLM cannot
    confidently classify the email.
    """

    __tablename__ = "action_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(sa.String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    is_fallback: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)


class TypeCategory(Base, TimestampMixin):
    """Layer 2 classification: what type of email is it?

    e.g. 'customer_support', 'sales_inquiry', 'billing', 'other' (fallback).
    The fallback category (is_fallback=True) is used when no specific type
    matches the email content.
    """

    __tablename__ = "type_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(sa.String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    is_fallback: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
