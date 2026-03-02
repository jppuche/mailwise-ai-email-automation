"""Routing rule and action models.

RoutingRule defines the conditions and actions for email routing.
RoutingAction records each dispatched (or attempted) routing action for an email.

JSONB fields use TypedDict to document the expected structure (tighten-types D1).
The DB stores them as JSONB so routing rules can be extended without schema changes.
"""

import datetime
import uuid
from enum import StrEnum
from typing import TypedDict

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, _enum_values


class RoutingConditions(TypedDict):
    """Structure for a single routing condition stored in the JSONB conditions array."""

    field: str  # "action_category" | "type_category" | "sender_domain" | "subject_contains"
    operator: str  # "eq" | "contains" | "in" | "not_in"
    value: str | list[str]


class RoutingActions(TypedDict):
    """Structure for a single routing action stored in the JSONB actions array."""

    channel: str  # "slack" | "email" | "hubspot"
    destination: str  # Channel ID, email address, or pipeline ID
    template_id: str | None


class RoutingActionStatus(StrEnum):
    """Execution status of a routing action attempt."""

    PENDING = "pending"
    DISPATCHED = "dispatched"
    FAILED = "failed"
    SKIPPED = "skipped"


class RoutingRule(Base, TimestampMixin):
    """A configurable rule that determines how matched emails are routed.

    Rules are evaluated in ascending priority order. The first matching active
    rule wins. conditions and actions are stored as JSONB arrays to allow
    multi-condition and multi-action rules without schema changes.
    """

    __tablename__ = "routing_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    priority: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, index=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    conditions: Mapped[list[RoutingConditions]] = mapped_column(JSONB, nullable=False)
    actions: Mapped[list[RoutingActions]] = mapped_column(JSONB, nullable=False)


class RoutingAction(Base, TimestampMixin):
    """Record of a routing action executed (or attempted) for an email.

    One RoutingAction row is created per dispatch attempt. rule_id is SET NULL
    if the rule is deleted — the action record is preserved for audit purposes.

    dispatch_id is a deterministic SHA-256[:32] hash of
    "{email_id}:{rule_id}:{channel}:{destination}" (B09 spec). This allows
    idempotent re-dispatch detection without querying the external channel.
    """

    __tablename__ = "routing_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("routing_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    channel: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    destination: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    priority: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status: Mapped[RoutingActionStatus] = mapped_column(
        sa.Enum(
            RoutingActionStatus,
            name="routingactionstatus",
            create_type=True,
            values_callable=_enum_values,
        ),
        nullable=False,
        default=RoutingActionStatus.PENDING,
    )
    dispatch_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True, index=True)
    dispatched_at: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
