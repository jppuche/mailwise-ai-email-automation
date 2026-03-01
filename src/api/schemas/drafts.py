"""Draft API schemas — list, detail, approve, reject, reassign."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from src.api.schemas.emails import ClassificationSummary


class DraftListItem(BaseModel):
    """Single draft in a paginated list."""

    id: uuid.UUID
    email_id: uuid.UUID
    email_subject: str
    email_sender: str
    status: str
    reviewer_id: uuid.UUID | None
    created_at: datetime


class EmailForDraftReview(BaseModel):
    """Email context for side-by-side draft review. No body_plain (PII)."""

    id: uuid.UUID
    subject: str
    sender_email: str
    sender_name: str | None
    snippet: str | None
    received_at: datetime
    classification: ClassificationSummary | None = None


class DraftDetailResponse(BaseModel):
    """Full draft detail for review."""

    id: uuid.UUID
    content: str
    status: str
    reviewer_id: uuid.UUID | None
    reviewed_at: datetime | None
    pushed_to_provider: bool
    email: EmailForDraftReview
    created_at: datetime
    updated_at: datetime


class DraftApproveRequest(BaseModel):
    """Request body for POST /drafts/{id}/approve."""

    push_to_gmail: bool = True


class DraftApproveResponse(BaseModel):
    """Response after approving a draft."""

    draft_id: uuid.UUID
    approved: bool
    gmail_draft_id: str | None = None
    approved_at: datetime
    note: str | None = None


class DraftRejectRequest(BaseModel):
    """Request body for POST /drafts/{id}/reject."""

    reason: str = Field(min_length=1)


class DraftReassignRequest(BaseModel):
    """Request body for POST /drafts/{id}/reassign."""

    reviewer_id: uuid.UUID
