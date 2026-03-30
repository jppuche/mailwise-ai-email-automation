"""Routing service data contracts.

These types are the boundary between the routing service and its callers.
ORM models are converted to Pydantic schemas before being passed to the
RuleEngine — the engine never imports ORM models directly.

No ``dict[str, Any]`` at boundaries.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel


class RoutingContext(BaseModel):
    """Classification context for rule evaluation — decoupled from ORM.

    Constructed by RoutingService from email + ClassificationResult DB records.
    The RuleEngine only knows RoutingContext — never SQLAlchemy models.
    """

    email_id: uuid.UUID
    action_slug: str
    type_slug: str
    confidence: Literal["high", "low"]
    sender_email: str
    sender_domain: str
    subject: str
    snippet: str
    sender_name: str | None = None


class RoutingRequest(BaseModel):
    """Input to the routing service."""

    email_id: uuid.UUID


class RoutingActionDef(BaseModel):
    """Action definition — decoupled from ORM RoutingActions TypedDict."""

    channel: str
    destination: str
    template_id: str | None = None


class RuleMatchResult(BaseModel):
    """A rule that matched + its actions to execute."""

    rule_id: uuid.UUID
    rule_name: str
    priority: int
    actions: list[RoutingActionDef]


class RoutingResult(BaseModel):
    """Complete result of routing an email."""

    email_id: uuid.UUID
    rules_matched: int
    rules_executed: int
    actions_dispatched: int
    actions_failed: int
    was_routed: bool
    routing_action_ids: list[uuid.UUID]
    final_state: str


class RuleTestResult(BaseModel):
    """Dry-run result — no dispatches, no state changes."""

    context: RoutingContext
    rules_matched: list[RuleMatchResult]
    would_dispatch: list[RoutingActionDef]
    total_actions: int
    dry_run: bool = True
