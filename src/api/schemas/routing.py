"""Routing rule API schemas — CRUD, reorder, test."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class RoutingConditionSchema(BaseModel):
    """A single routing condition."""

    field: str
    operator: str
    value: str | list[str]


class RoutingActionSchema(BaseModel):
    """A single routing action definition."""

    channel: str
    destination: str
    template_id: str | None = None


class RoutingRuleCreate(BaseModel):
    """Request body for POST /routing-rules."""

    name: str = Field(min_length=1, max_length=255)
    is_active: bool = True
    conditions: list[RoutingConditionSchema] = Field(min_length=1)
    actions: list[RoutingActionSchema] = Field(min_length=1)


class RoutingRuleUpdate(BaseModel):
    """Request body for PUT /routing-rules/{id}. All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None
    conditions: list[RoutingConditionSchema] | None = None
    actions: list[RoutingActionSchema] | None = None


class RoutingRuleResponse(BaseModel):
    """Response schema for a routing rule."""

    id: uuid.UUID
    name: str
    is_active: bool
    priority: int
    conditions: list[RoutingConditionSchema]
    actions: list[RoutingActionSchema]
    created_at: datetime
    updated_at: datetime


class RoutingRuleReorderRequest(BaseModel):
    """Reorder request — ordered_ids[0] gets priority 1."""

    ordered_ids: list[uuid.UUID] = Field(min_length=1)


class RuleTestRequest(BaseModel):
    """Input for POST /routing-rules/test dry-run."""

    email_id: uuid.UUID
    action_slug: str
    type_slug: str
    confidence: str
    sender_email: str
    sender_domain: str
    subject: str
    snippet: str
    sender_name: str | None = None


class RuleTestMatchResponse(BaseModel):
    """A single matched rule in the dry-run response."""

    rule_id: uuid.UUID
    rule_name: str
    priority: int
    would_dispatch: list[RoutingActionSchema]


class RuleTestResponse(BaseModel):
    """Response for POST /routing-rules/test dry-run."""

    matching_rules: list[RuleTestMatchResponse]
    total_rules_evaluated: int
    total_actions: int
    dry_run: bool = True
