"""Routing rules router — CRUD, reorder, and dry-run test.

Architecture:
  - ZERO try/except — domain exceptions propagate to exception_handlers.py.
  - Admin only for all endpoints.
  - Route ordering: literal paths (reorder, test) BEFORE parameterized (/{rule_id}).

Endpoints:
  PUT    /reorder       — bulk re-prioritize rules (literal path, must come first)
  POST   /test          — dry-run rule evaluation (literal path, must come first)
  GET    /              — list all rules ordered by priority
  POST   /              — create a new rule (201)
  GET    /{rule_id}     — get a single rule
  PUT    /{rule_id}     — update a rule (partial)
  DELETE /{rule_id}     — delete a rule (204)
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_routing_service, require_admin
from src.api.schemas.routing import (
    RoutingActionSchema,
    RoutingConditionSchema,
    RoutingRuleCreate,
    RoutingRuleReorderRequest,
    RoutingRuleResponse,
    RoutingRuleUpdate,
    RuleTestMatchResponse,
    RuleTestRequest,
    RuleTestResponse,
)
from src.core.database import get_async_db
from src.core.exceptions import NotFoundError
from src.models.routing import RoutingRule
from src.models.user import User
from src.services.routing import RoutingService
from src.services.schemas.routing import RoutingContext

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["routing-rules"])


def _rule_to_response(rule: RoutingRule) -> RoutingRuleResponse:
    """Map a RoutingRule ORM object to the API response schema."""
    conditions = [RoutingConditionSchema(**c) for c in rule.conditions]
    actions = [RoutingActionSchema(**a) for a in rule.actions]
    return RoutingRuleResponse(
        id=rule.id,
        name=rule.name,
        is_active=rule.is_active,
        priority=rule.priority,
        conditions=conditions,
        actions=actions,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


# --- LITERAL PATHS FIRST (before /{rule_id}) to avoid path param collision ---


@router.put("/reorder", response_model=list[RoutingRuleResponse])
async def reorder_rules(
    body: RoutingRuleReorderRequest,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> list[RoutingRuleResponse]:
    """Bulk re-prioritize routing rules.

    ordered_ids[0] receives priority 1. All provided rule IDs must exist.
    Raises NotFoundError if any ID is missing.
    """
    # Load all rules whose IDs are in ordered_ids
    result = await db.execute(select(RoutingRule).where(RoutingRule.id.in_(body.ordered_ids)))
    rules_found = {r.id: r for r in result.scalars().all()}

    # Verify all IDs exist
    missing = [rid for rid in body.ordered_ids if rid not in rules_found]
    if missing:
        raise NotFoundError(f"Routing rule(s) not found: {', '.join(str(i) for i in missing)}")

    # Assign priorities in requested order
    for idx, rule_id in enumerate(body.ordered_ids):
        rules_found[rule_id].priority = idx + 1

    await db.flush()

    # Return in new priority order
    return [_rule_to_response(rules_found[rid]) for rid in body.ordered_ids]


@router.post("/test", response_model=RuleTestResponse)
async def test_rules(
    body: RuleTestRequest,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
    routing_service: RoutingService = Depends(get_routing_service),  # noqa: B008
) -> RuleTestResponse:
    """Dry-run rule evaluation against a synthetic email context.

    No RoutingActions created, no dispatches performed, no email state changed.
    """
    context = RoutingContext(
        email_id=body.email_id,
        action_slug=body.action_slug,
        type_slug=body.type_slug,
        confidence=body.confidence,
        sender_email=body.sender_email,
        sender_domain=body.sender_domain,
        subject=body.subject,
        snippet=body.snippet,
        sender_name=body.sender_name,
    )

    test_result = await routing_service.test_route(context, db)

    matching_rules = [
        RuleTestMatchResponse(
            rule_id=match.rule_id,
            rule_name=match.rule_name,
            priority=match.priority,
            would_dispatch=[
                RoutingActionSchema(
                    channel=action.channel,
                    destination=action.destination,
                    template_id=action.template_id,
                )
                for action in match.actions
            ],
        )
        for match in test_result.rules_matched
    ]

    return RuleTestResponse(
        matching_rules=matching_rules,
        total_rules_evaluated=len(test_result.rules_matched),
        total_actions=test_result.total_actions,
        dry_run=True,
    )


# --- PARAMETERIZED ROUTES ---


@router.get("/", response_model=list[RoutingRuleResponse])
async def list_rules(
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> list[RoutingRuleResponse]:
    """List all routing rules ordered by priority ascending."""
    result = await db.execute(select(RoutingRule).order_by(RoutingRule.priority.asc()))
    rules = list(result.scalars().all())
    return [_rule_to_response(r) for r in rules]


@router.post("/", response_model=RoutingRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: RoutingRuleCreate,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> RoutingRuleResponse:
    """Create a new routing rule.

    Priority auto-assigned as MAX(priority) + 1. If no rules exist, priority = 1.
    """
    # Auto-assign priority
    max_result = await db.execute(select(func.max(RoutingRule.priority)))
    max_priority: int | None = max_result.scalar_one_or_none()
    next_priority = (max_priority or 0) + 1

    rule = RoutingRule(
        id=uuid.uuid4(),
        name=body.name,
        is_active=body.is_active,
        priority=next_priority,
        conditions=[c.model_dump() for c in body.conditions],
        actions=[a.model_dump() for a in body.actions],
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)

    logger.info("routing_rule_created", rule_id=str(rule.id), name=rule.name)
    return _rule_to_response(rule)


@router.get("/{rule_id}", response_model=RoutingRuleResponse)
async def get_rule(
    rule_id: uuid.UUID,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> RoutingRuleResponse:
    """Get a single routing rule by ID."""
    result = await db.execute(select(RoutingRule).where(RoutingRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise NotFoundError(f"Routing rule {rule_id} not found")
    return _rule_to_response(rule)


@router.put("/{rule_id}", response_model=RoutingRuleResponse)
async def update_rule(
    rule_id: uuid.UUID,
    body: RoutingRuleUpdate,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> RoutingRuleResponse:
    """Partial update of a routing rule. Only non-None fields are applied."""
    result = await db.execute(select(RoutingRule).where(RoutingRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise NotFoundError(f"Routing rule {rule_id} not found")

    if body.name is not None:
        rule.name = body.name
    if body.is_active is not None:
        rule.is_active = body.is_active
    if body.conditions is not None:
        rule.conditions = [c.model_dump() for c in body.conditions]  # type: ignore[misc]
    if body.actions is not None:
        rule.actions = [a.model_dump() for a in body.actions]  # type: ignore[misc]

    await db.flush()
    await db.refresh(rule)

    logger.info("routing_rule_updated", rule_id=str(rule_id))
    return _rule_to_response(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: uuid.UUID,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> None:
    """Delete a routing rule. Returns 204 No Content."""
    result = await db.execute(select(RoutingRule).where(RoutingRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise NotFoundError(f"Routing rule {rule_id} not found")

    await db.delete(rule)
    logger.info("routing_rule_deleted", rule_id=str(rule_id))
