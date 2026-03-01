"""Category, few-shot example, and feedback API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ActionCategoryCreate(BaseModel):
    """Request body for POST /categories/actions."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=100)
    description: str = ""
    is_fallback: bool = False
    is_active: bool = True


class ActionCategoryUpdate(BaseModel):
    """Request body for PUT /categories/actions/{id}. Slug is immutable."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    is_fallback: bool | None = None
    is_active: bool | None = None


class ActionCategoryResponse(BaseModel):
    """Response schema for an action category."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    description: str
    is_fallback: bool
    is_active: bool
    display_order: int
    created_at: datetime
    updated_at: datetime


# TypeCategory — same structure
TypeCategoryCreate = ActionCategoryCreate
TypeCategoryUpdate = ActionCategoryUpdate
TypeCategoryResponse = ActionCategoryResponse


class ReorderRequest(BaseModel):
    """Ordered list of IDs: index defines new display_order."""

    ordered_ids: list[uuid.UUID]

    @field_validator("ordered_ids")
    @classmethod
    def must_be_nonempty(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if not v:
            raise ValueError("ordered_ids must not be empty")
        return v


class FewShotExampleCreate(BaseModel):
    """Request body for POST /classification/examples."""

    model_config = ConfigDict(extra="forbid")

    email_snippet: str = Field(min_length=1)
    action_slug: str = Field(min_length=1, max_length=100)
    type_slug: str = Field(min_length=1, max_length=100)
    rationale: str | None = None


class FewShotExampleUpdate(BaseModel):
    """Request body for PUT /classification/examples/{id}."""

    model_config = ConfigDict(extra="forbid")

    email_snippet: str | None = Field(default=None, min_length=1)
    action_slug: str | None = Field(default=None, min_length=1, max_length=100)
    type_slug: str | None = Field(default=None, min_length=1, max_length=100)
    rationale: str | None = None
    is_active: bool | None = None


class FewShotExampleResponse(BaseModel):
    """Response schema for a few-shot example."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email_snippet: str
    action_slug: str
    type_slug: str
    rationale: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class FeedbackItem(BaseModel):
    """Read-only representation of a classification correction."""

    id: uuid.UUID
    email_id: uuid.UUID
    original_action: str
    original_type: str
    corrected_action: str
    corrected_type: str
    corrected_by: uuid.UUID
    corrected_at: datetime
