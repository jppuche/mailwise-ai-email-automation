"""Draft generation service data contracts.

tighten-types D1: No ``dict[str, Any]`` at boundaries.
All fields are fully typed with specific types.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class EmailContent(BaseModel):
    """Email data for draft context — privacy-safe (body_snippet, not body_plain)."""

    sender_email: str
    sender_name: str | None = None
    subject: str
    body_snippet: str  # truncated to max_body_length — NEVER full body_plain
    received_at: str  # ISO 8601


class ClassificationContext(BaseModel):
    """Classification metadata for prompt context."""

    action: str  # ActionCategory slug
    type: str  # TypeCategory slug
    confidence: str  # "high" | "low"


class CRMContextData(BaseModel):
    """CRM data available for draft context.

    Note: Only ``contact_id`` is populated from CRMSyncRecord (B10).
    Other fields remain None/[] until CRM adapter enrichment is added.
    """

    contact_name: str | None = None
    company: str | None = None
    account_tier: str | None = None
    recent_interactions: list[str] = []  # summaries, not objects
    contact_id: str | None = None


class OrgContext(BaseModel):
    """Organization-level draft configuration."""

    system_prompt: str
    tone: str
    signature: str | None = None
    prohibited_language: list[str] = []


class DraftContext(BaseModel):
    """Complete context assembled by DraftContextBuilder for LLM prompt."""

    email_content: EmailContent
    classification: ClassificationContext
    crm_context: CRMContextData | None = None
    org_context: OrgContext
    template: str | None = None
    notes: list[str] = []


class DraftRequest(BaseModel):
    """Input to DraftGenerationService.generate()."""

    email_id: uuid.UUID
    email_content: EmailContent
    classification: ClassificationContext
    template_id: str | None = None
    push_to_gmail: bool = False


class DraftResult(BaseModel):
    """Complete result of one draft generation attempt."""

    email_id: uuid.UUID
    draft_id: uuid.UUID | None = None
    gmail_draft_id: str | None = None  # DraftId is NewType(str), str compatible
    status: str  # "generated" | "failed" | "generated_push_failed"
    model_used: str | None = None
    fallback_applied: bool = False
    error_detail: str | None = None


class DraftGenerationConfig(BaseModel):
    """All values sourced from Settings (Cat 8)."""

    push_to_gmail: bool
    org_context: OrgContext
    retry_max: int
