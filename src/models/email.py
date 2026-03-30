"""Email model and state machine.

The Email model is the central entity in the mailwise pipeline. Its state
column enforces the processing pipeline via a PostgreSQL ENUM type — the DB
rejects any value outside the enum, providing a second enforcement layer
beyond the Python-level transition_to() method.

State machine: FETCHED -> SANITIZED -> CLASSIFIED -> ROUTED -> CRM_SYNCED
               -> DRAFT_GENERATED -> COMPLETED -> RESPONDED (terminal)

Error states have recovery paths back to the last successful state.
"""

import datetime
import uuid
from enum import StrEnum
from typing import TypedDict

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.exceptions import InvalidStateTransitionError
from src.models.base import Base, TimestampMixin


class EmailState(StrEnum):
    """Processing state of an email in the mailwise pipeline.

    Stored as a PostgreSQL ENUM type (not VARCHAR) to enforce valid values
    at the database level. See VALID_TRANSITIONS for allowed transitions.
    """

    # Happy path
    FETCHED = "FETCHED"
    SANITIZED = "SANITIZED"
    CLASSIFIED = "CLASSIFIED"
    ROUTED = "ROUTED"
    CRM_SYNCED = "CRM_SYNCED"
    DRAFT_GENERATED = "DRAFT_GENERATED"
    COMPLETED = "COMPLETED"
    RESPONDED = "RESPONDED"

    # Error states — each has a recovery path
    CLASSIFICATION_FAILED = "CLASSIFICATION_FAILED"
    ROUTING_FAILED = "ROUTING_FAILED"
    CRM_SYNC_FAILED = "CRM_SYNC_FAILED"
    DRAFT_FAILED = "DRAFT_FAILED"


VALID_TRANSITIONS: dict[EmailState, frozenset[EmailState]] = {
    EmailState.FETCHED: frozenset({EmailState.SANITIZED}),
    EmailState.SANITIZED: frozenset({EmailState.CLASSIFIED, EmailState.CLASSIFICATION_FAILED}),
    EmailState.CLASSIFIED: frozenset({EmailState.ROUTED, EmailState.ROUTING_FAILED}),
    EmailState.ROUTED: frozenset({EmailState.CRM_SYNCED, EmailState.CRM_SYNC_FAILED}),
    EmailState.CRM_SYNCED: frozenset({EmailState.DRAFT_GENERATED, EmailState.DRAFT_FAILED}),
    EmailState.DRAFT_GENERATED: frozenset({EmailState.COMPLETED}),
    EmailState.COMPLETED: frozenset({EmailState.RESPONDED}),
    EmailState.RESPONDED: frozenset(),  # Terminal state — no valid transitions
    # Recovery paths from error states
    EmailState.CLASSIFICATION_FAILED: frozenset({EmailState.SANITIZED}),
    EmailState.ROUTING_FAILED: frozenset({EmailState.CLASSIFIED}),
    EmailState.CRM_SYNC_FAILED: frozenset({EmailState.ROUTED}),
    EmailState.DRAFT_FAILED: frozenset({EmailState.CRM_SYNCED}),
}


class RecipientData(TypedDict):
    """Structure for a single recipient in the recipients JSONB field."""

    email: str
    name: str
    type: str  # "to" | "cc" | "bcc"


class AttachmentData(TypedDict):
    """Structure for a single attachment in the attachments JSONB field."""

    filename: str
    mime_type: str
    size_bytes: int
    attachment_id: str


class Email(Base, TimestampMixin):
    """Persisted email fetched from a provider (e.g. Gmail).

    The state column drives the pipeline: each Celery task reads the current
    state, does its work, then calls transition_to() before committing.
    """

    __tablename__ = "emails"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_message_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, unique=True)
    thread_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True, index=True)
    account: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    sender_email: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    sender_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    recipients: Mapped[list[RecipientData]] = mapped_column(JSONB, nullable=False, default=list)
    subject: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    body_plain: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    date: Mapped[datetime.datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    attachments: Mapped[list[AttachmentData]] = mapped_column(JSONB, nullable=False, default=list)
    provider_labels: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    state: Mapped[EmailState] = mapped_column(
        sa.Enum(EmailState, name="emailstate", create_type=True),
        nullable=False,
        default=EmailState.FETCHED,
        index=True,
    )
    processed_at: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        sa.Index("ix_emails_state_date", "state", "date"),
        sa.Index("ix_emails_account_state", "account", "state"),
    )

    def transition_to(self, new_state: EmailState) -> None:
        """Transition this email to a new pipeline state.

        Invariants:
          - self.state is the current persisted state of the email.
          - new_state must be reachable from self.state via VALID_TRANSITIONS.

        Guarantees:
          - If the transition is valid, self.state is updated to new_state.
          - The DB commit is the caller's responsibility — this method only
            mutates the in-memory object.

        Errors:
          - Raises InvalidStateTransitionError if new_state is not in
            VALID_TRANSITIONS[self.state]. This is a programmer error (logic
            bug), not an operational error. Callers MUST NOT catch this.

        State transitions:
          - self.state = new_state (in-memory only; caller must commit to DB).
        """
        allowed = VALID_TRANSITIONS.get(self.state, frozenset())
        if new_state not in allowed:
            raise InvalidStateTransitionError(
                f"Cannot transition Email {self.id} from {self.state} to {new_state}. "
                f"Allowed: {allowed}"
            )
        self.state = new_state
