"""Email API schemas — list, detail, retry, reclassify, classification, feedback."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from src.models.email import EmailState


class PaginationParams(BaseModel):
    """Query-string pagination parameters."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class EmailFilter(BaseModel):
    """Optional filters for email list."""

    state: EmailState | None = None
    action: str | None = None
    type: str | None = None
    sender: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class ClassificationSummary(BaseModel):
    """Classification metadata for list and detail views."""

    action: str
    type: str
    confidence: str
    is_fallback: bool


class RoutingActionSummary(BaseModel):
    """Routing action summary for email detail."""

    id: uuid.UUID
    channel: str
    destination: str
    status: str
    dispatched_at: datetime | None


class CRMSyncSummary(BaseModel):
    """CRM sync status summary."""

    status: str
    contact_id: str | None
    activity_id: str | None
    synced_at: datetime | None


class DraftSummary(BaseModel):
    """Draft summary for email detail."""

    id: uuid.UUID
    status: str
    created_at: datetime


class EmailListItem(BaseModel):
    """Single email in a paginated list. No body_plain (PII policy)."""

    id: uuid.UUID
    subject: str
    sender_email: str
    sender_name: str | None
    received_at: datetime
    state: EmailState
    snippet: str | None
    classification: ClassificationSummary | None = None


class EmailDetailResponse(BaseModel):
    """Full email detail including all pipeline stages."""

    id: uuid.UUID
    subject: str
    sender_email: str
    sender_name: str | None
    received_at: datetime
    state: EmailState
    snippet: str | None
    thread_id: str | None
    classification: ClassificationSummary | None = None
    routing_actions: list[RoutingActionSummary] = []
    crm_sync: CRMSyncSummary | None = None
    draft: DraftSummary | None = None
    created_at: datetime
    updated_at: datetime


class RetryRequest(BaseModel):
    """Request body for POST /emails/{id}/retry."""

    reason: str | None = None


class RetryResponse(BaseModel):
    """Response for retry action."""

    queued: bool
    message: str
    email_id: uuid.UUID


class ReclassifyRequest(BaseModel):
    """Request body for POST /emails/{id}/reclassify."""

    reason: str | None = None


class ReclassifyResponse(BaseModel):
    """Response for reclassify action."""

    queued: bool
    message: str
    email_id: uuid.UUID


class ClassificationDetailResponse(BaseModel):
    """Full classification result for GET /emails/{id}/classification."""

    id: uuid.UUID
    email_id: uuid.UUID
    action: str
    type: str
    confidence: str
    is_fallback: bool
    classified_at: datetime


class ClassificationFeedbackRequest(BaseModel):
    """Request body for POST /emails/{id}/classification/feedback."""

    corrected_action: str = Field(min_length=1)
    corrected_type: str = Field(min_length=1)


class FeedbackResponse(BaseModel):
    """Response after submitting feedback."""

    recorded: bool
    feedback_id: uuid.UUID
