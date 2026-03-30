"""Routing service — orchestrates rule evaluation, dispatch, and state transition.

Evaluates routing rules in priority order against classified emails, dispatches to
channel adapters with idempotent dispatch IDs, records each RoutingAction independently,
and manages partial failures without reverting successful dispatches.

Invariants: Email must be in CLASSIFIED state. Channel adapters registered at construction.
Guarantees: route() transitions email to ROUTED or ROUTING_FAILED. Each RoutingAction
  has its own db.commit(). Partial failure in action N does not revert N-1.
Errors raised: ValueError (email not found, adapter not found),
  InvalidStateTransitionError (wrong state), SQLAlchemyError (DB failures).
Errors silenced: Channel adapter errors per-action (recorded as FAILED).
External state: PostgreSQL (rules, actions, email state), channel adapters.

External-state ops (DB, channel adapters): structured try/except with specific types.
Local computation (rule eval, dispatch_id, payload build, priority, state): no try/except.

Each RoutingAction commits independently — failure in N does not revert N-1.
Single state transition at end (ROUTED or ROUTING_FAILED), not per-action.
All defaults from Settings (env vars), no hardcoded values in service.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Literal

import structlog
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.channel.base import ChannelAdapter
from src.adapters.channel.exceptions import (
    ChannelAuthError,
    ChannelConnectionError,
    ChannelDeliveryError,
    ChannelRateLimitError,
)
from src.adapters.channel.schemas import (
    ClassificationInfo,
    DeliveryResult,
    RoutingPayload,
    SenderInfo,
)
from src.core.config import Settings
from src.core.exceptions import InvalidStateTransitionError
from src.models.category import ActionCategory, TypeCategory
from src.models.classification import ClassificationResult
from src.models.email import Email, EmailState
from src.models.routing import RoutingAction, RoutingActionStatus, RoutingRule
from src.services.rule_engine import RuleEngine
from src.services.schemas.routing import (
    RoutingActionDef,
    RoutingContext,
    RoutingResult,
    RuleMatchResult,
    RuleTestResult,
)

logger = structlog.get_logger(__name__)

# VIP escalation keywords (module-level frozenset, not free-form strings)
URGENT_KEYWORDS: frozenset[str] = frozenset(
    {"urgent", "asap", "immediately", "legal", "security breach"}
)


class RoutingService:
    """Orchestrates email routing: rules → evaluate → dispatch → record → transition.

    Invariants:
      - ``channel_adapters`` must contain at least one adapter.
      - ``settings`` provides all configurable defaults.

    Guarantees:
      - ``route()`` transitions email to ROUTED or ROUTING_FAILED.
      - Each RoutingAction has its own ``db.commit()``.
      - Partial failure: action N failure does not revert action N-1.

    Errors raised:
      - ValueError: email not found, adapter not registered for channel.
      - InvalidStateTransitionError: email not in CLASSIFIED state.
      - SQLAlchemyError: DB failures during load or state transition.

    Errors silenced:
      - Channel adapter errors per-action: recorded as FAILED RoutingAction.
    """

    def __init__(
        self,
        *,
        channel_adapters: dict[str, ChannelAdapter],
        settings: Settings,
    ) -> None:
        self._channel_adapters = channel_adapters
        self._settings = settings
        self._rule_engine = RuleEngine()
        self._vip_senders = _parse_vip_senders(settings.routing_vip_senders)

    async def route(
        self,
        email_id: uuid.UUID,
        db: AsyncSession,
    ) -> RoutingResult:
        """Route a classified email through matching rules.

        Preconditions:
          - Email with email_id exists in DB with state=CLASSIFIED.
          - ClassificationResult DB record exists for email_id.
          - At least one ChannelAdapter registered in the service.

        Errors raised on violation:
          - ValueError if email_id not found.
          - InvalidStateTransitionError if email.state != CLASSIFIED.

        External state errors:
          - SQLAlchemyError loading rules — aborts routing; email stays CLASSIFIED.
          - ChannelAdapterError per rule — recorded as FAILED; routing continues.

        Errors silenced:
          - None — all channel failures recorded in RoutingAction.status=FAILED.
        """
        # Load email
        email = await self._load_email_or_raise(email_id, db)

        # State check
        if email.state != EmailState.CLASSIFIED:
            raise InvalidStateTransitionError(
                f"Email {email_id} must be CLASSIFIED to route, got {email.state}"
            )

        # Build RoutingContext from email + classification DB records
        context = await self._build_routing_context(email, db)

        # Load active rules
        rules = await self._load_active_rules(db)

        # Evaluate rules
        matches = self._rule_engine.evaluate(context, rules)

        # Dispatch all matched rule actions
        all_action_ids: list[uuid.UUID] = []
        dispatched_count = 0
        failed_count = 0

        for match in matches:
            action_ids, dispatched, failed = await self._dispatch_rule_actions(
                context, match, email, db
            )
            all_action_ids.extend(action_ids)
            dispatched_count += dispatched
            failed_count += failed

        # Determine final state
        if len(matches) == 0:
            new_state = EmailState.ROUTED  # Unrouted is valid, not error
        elif dispatched_count > 0:
            new_state = EmailState.ROUTED
        else:
            new_state = EmailState.ROUTING_FAILED

        # Transition email state
        email.transition_to(new_state)
        await db.commit()

        final_state_str = "ROUTED" if new_state == EmailState.ROUTED else "ROUTING_FAILED"

        logger.info(
            "routing_complete",
            email_id=str(email_id),
            rules_matched=len(matches),
            dispatched=dispatched_count,
            failed=failed_count,
            final_state=final_state_str,
        )

        return RoutingResult(
            email_id=email_id,
            rules_matched=len(matches),
            rules_executed=len(matches),
            actions_dispatched=dispatched_count,
            actions_failed=failed_count,
            was_routed=new_state == EmailState.ROUTED,
            routing_action_ids=all_action_ids,
            final_state=final_state_str,
        )

    async def test_route(
        self,
        context: RoutingContext,
        db: AsyncSession,
    ) -> RuleTestResult:
        """Dry-run of the rule engine.

        GUARANTEE: No RoutingAction created, no adapter called, no email state changed.
        Useful for users to validate rules before activating them.

        Preconditions:
          - context is a valid RoutingContext.

        Errors raised:
          - SQLAlchemyError loading rules — re-raised to caller.

        Errors silenced: None.
        """
        # Load active rules
        rules = await self._load_active_rules(db)

        # Evaluate
        matches = self._rule_engine.evaluate(context, rules)

        would_dispatch: list[RoutingActionDef] = [
            action for match in matches for action in match.actions
        ]

        return RuleTestResult(
            context=context,
            rules_matched=matches,
            would_dispatch=would_dispatch,
            total_actions=len(would_dispatch),
        )

    async def _load_email_or_raise(
        self,
        email_id: uuid.UUID,
        db: AsyncSession,
    ) -> Email:
        """Load email from DB or raise ValueError."""
        result = await db.execute(select(Email).where(Email.id == email_id))
        email = result.scalar_one_or_none()
        if email is None:
            raise ValueError(f"Email {email_id} not found")
        return email

    async def _build_routing_context(
        self,
        email: Email,
        db: AsyncSession,
    ) -> RoutingContext:
        """Build RoutingContext from email + ClassificationResult DB records.

        Reads ClassificationResult, ActionCategory, TypeCategory from DB.
        """
        # Load classification result
        cr_result = await db.execute(
            select(ClassificationResult).where(ClassificationResult.email_id == email.id)
        )
        cr = cr_result.scalar_one_or_none()
        if cr is None:
            raise ValueError(f"ClassificationResult not found for email {email.id}")

        # Resolve category slugs
        action_result = await db.execute(
            select(ActionCategory.slug).where(ActionCategory.id == cr.action_category_id)
        )
        action_slug = action_result.scalar_one_or_none()
        if action_slug is None:
            raise ValueError(
                f"ActionCategory {cr.action_category_id} not found for email {email.id}"
            )

        type_result = await db.execute(
            select(TypeCategory.slug).where(TypeCategory.id == cr.type_category_id)
        )
        type_slug = type_result.scalar_one_or_none()
        if type_slug is None:
            raise ValueError(f"TypeCategory {cr.type_category_id} not found for email {email.id}")

        sender_domain = email.sender_email.split("@")[-1]

        return RoutingContext(
            email_id=email.id,
            action_slug=action_slug,
            type_slug=type_slug,
            confidence="high" if cr.confidence.value == "high" else "low",
            sender_email=email.sender_email,
            sender_domain=sender_domain,
            subject=email.subject,
            snippet=email.snippet or "",
            sender_name=email.sender_name,
        )

    async def _load_active_rules(self, db: AsyncSession) -> list[RoutingRule]:
        """Load active routing rules ordered by priority DESC."""
        result = await db.execute(
            select(RoutingRule)
            .where(RoutingRule.is_active.is_(True))
            .order_by(RoutingRule.priority.desc())
        )
        return list(result.scalars().all())

    async def _dispatch_rule_actions(
        self,
        context: RoutingContext,
        match: RuleMatchResult,
        email: Email,
        db: AsyncSession,
    ) -> tuple[list[uuid.UUID], int, int]:
        """Dispatch all actions for a matched rule.

        Each action is independent: failure in action N does not stop action N+1.
        Each RoutingAction has its own db.commit().

        Returns: (action_ids, dispatched_count, failed_count)
        """
        action_ids: list[uuid.UUID] = []
        dispatched = 0
        failed = 0

        for action_def in match.actions:
            dispatch_id = _compute_dispatch_id(
                context.email_id, match.rule_id, action_def.channel, action_def.destination
            )

            # Check idempotency
            try:
                existing = await self._find_existing_dispatch(dispatch_id, db)
            except SQLAlchemyError as exc:
                logger.error(
                    "dispatch_idempotency_check_failed",
                    dispatch_id=dispatch_id,
                    error=str(exc),
                )
                failed += 1
                continue

            if existing is not None and existing.status == RoutingActionStatus.DISPATCHED:
                logger.info("dispatch_skipped_already_dispatched", dispatch_id=dispatch_id)
                action_ids.append(existing.id)
                dispatched += 1
                continue

            # Resolve adapter
            adapter = self._get_adapter(action_def.channel)
            if adapter is None:
                logger.error("no_adapter_for_channel", channel=action_def.channel)
                await self._record_failed_action(
                    db,
                    context,
                    match,
                    action_def,
                    dispatch_id,
                    error=f"No adapter registered for channel '{action_def.channel}'",
                )
                failed += 1
                continue

            # Build payload
            payload = self._build_routing_payload(context, action_def, match)

            # Dispatch
            delivery_result: DeliveryResult | None = None
            dispatch_error: str | None = None

            try:
                delivery_result = await adapter.send_notification(payload, action_def.destination)
            except ChannelAuthError as exc:
                dispatch_error = str(exc)
                logger.error("channel_auth_error", channel=action_def.channel, error=str(exc))
            except ChannelRateLimitError as exc:
                dispatch_error = str(exc)
                logger.warning(
                    "channel_rate_limited",
                    channel=action_def.channel,
                    retry_after=exc.retry_after_seconds,
                )
            except ChannelConnectionError as exc:
                dispatch_error = str(exc)
                logger.error("channel_connection_error", channel=action_def.channel, error=str(exc))
            except ChannelDeliveryError as exc:
                dispatch_error = str(exc)
                logger.error("channel_delivery_error", channel=action_def.channel, error=str(exc))

            if dispatch_error is not None:
                await self._record_failed_action(
                    db, context, match, action_def, dispatch_id, error=dispatch_error
                )
                failed += 1
                continue

            # Record success
            assert delivery_result is not None
            try:
                action_id = await self._record_success_action(
                    db,
                    context,
                    match,
                    action_def,
                    dispatch_id,
                    message_ts=delivery_result.message_ts,
                )
                action_ids.append(action_id)
                dispatched += 1
            except SQLAlchemyError as exc:
                logger.error(
                    "routing_action_persist_failed",
                    dispatch_id=dispatch_id,
                    error=str(exc),
                )
                failed += 1

        return action_ids, dispatched, failed

    async def _find_existing_dispatch(
        self, dispatch_id: str, db: AsyncSession
    ) -> RoutingAction | None:
        """Check if a RoutingAction with this dispatch_id already exists."""
        result = await db.execute(
            select(RoutingAction).where(RoutingAction.dispatch_id == dispatch_id)
        )
        return result.scalar_one_or_none()

    def _get_adapter(self, channel: str) -> ChannelAdapter | None:
        """Look up adapter by channel name."""
        return self._channel_adapters.get(channel)

    def _build_routing_payload(
        self,
        context: RoutingContext,
        action_def: RoutingActionDef,
        match: RuleMatchResult,
    ) -> RoutingPayload:
        """Build RoutingPayload from context. Local computation — no try/except."""
        priority = _determine_dispatch_priority(context, match.priority, self._vip_senders)

        return RoutingPayload(
            email_id=str(context.email_id),
            subject=context.subject,
            sender=SenderInfo(email=context.sender_email, name=context.sender_name),
            classification=ClassificationInfo(
                action=context.action_slug,
                type=context.type_slug,
                confidence=context.confidence,
            ),
            priority=priority,
            snippet=context.snippet[: self._settings.routing_snippet_length],
            dashboard_link=(
                f"{self._settings.routing_dashboard_base_url}/emails/{context.email_id}"
            ),
            timestamp=datetime.now(UTC),
        )

    async def _record_failed_action(
        self,
        db: AsyncSession,
        context: RoutingContext,
        match: RuleMatchResult,
        action_def: RoutingActionDef,
        dispatch_id: str,
        *,
        error: str,
    ) -> None:
        """Record a failed RoutingAction with its own independent commit."""
        priority = _determine_dispatch_priority(context, match.priority, self._vip_senders)
        action = RoutingAction(
            id=uuid.uuid4(),
            email_id=context.email_id,
            rule_id=match.rule_id,
            channel=action_def.channel,
            destination=action_def.destination,
            priority=_priority_to_int(priority),
            status=RoutingActionStatus.FAILED,
            dispatch_id=dispatch_id,
            dispatched_at=None,
            attempts=1,
        )
        try:
            db.add(action)
            await db.commit()
        except SQLAlchemyError as exc:
            await db.rollback()
            logger.error("failed_action_persist_error", dispatch_id=dispatch_id, error=str(exc))

    async def _record_success_action(
        self,
        db: AsyncSession,
        context: RoutingContext,
        match: RuleMatchResult,
        action_def: RoutingActionDef,
        dispatch_id: str,
        *,
        message_ts: str | None,
    ) -> uuid.UUID:
        """Record a successful RoutingAction with its own independent commit."""
        priority = _determine_dispatch_priority(context, match.priority, self._vip_senders)
        action_id = uuid.uuid4()
        action = RoutingAction(
            id=action_id,
            email_id=context.email_id,
            rule_id=match.rule_id,
            channel=action_def.channel,
            destination=action_def.destination,
            priority=_priority_to_int(priority),
            status=RoutingActionStatus.DISPATCHED,
            dispatch_id=dispatch_id,
            dispatched_at=datetime.now(UTC),
            attempts=1,
        )
        db.add(action)
        await db.commit()
        return action_id


def _compute_dispatch_id(
    email_id: uuid.UUID,
    rule_id: uuid.UUID,
    channel: str,
    destination: str,
) -> str:
    """SHA-256[:32] of ``"{email_id}:{rule_id}:{channel}:{destination}"``.

    Pure local computation — deterministic, no try/except.
    Same input always produces same dispatch_id.
    """
    raw = f"{email_id}:{rule_id}:{channel}:{destination}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _parse_vip_senders(vip_str: str) -> frozenset[str]:
    """Parse comma-separated VIP senders/domains to frozenset."""
    if not vip_str:
        return frozenset()
    return frozenset(s.strip().lower() for s in vip_str.split(",") if s.strip())


def _vip_domains(vip_senders: frozenset[str]) -> frozenset[str]:
    """Extract domain patterns (e.g. '*.company.com') from VIP senders."""
    return frozenset(
        s[1:]  # strip leading '*' → '.company.com'
        for s in vip_senders
        if s.startswith("*.")
    )


def _determine_dispatch_priority(
    context: RoutingContext,
    rule_priority: int,
    vip_senders: frozenset[str],
) -> Literal["urgent", "normal", "low"]:
    """Determine dispatch priority. Local computation — conditionals only."""
    # 1. VIP sender: highest priority always
    if context.sender_email.lower() in vip_senders:
        return "urgent"
    vip_doms = _vip_domains(vip_senders)
    if any(context.sender_domain.lower().endswith(d) for d in vip_doms):
        return "urgent"

    # 2. Classification-based: urgent action slug
    if context.action_slug == "escalate":
        return "urgent"

    # 3. Keyword escalation in subject
    if any(kw in context.subject.lower() for kw in URGENT_KEYWORDS):
        return "urgent"

    # 4. Rule priority ranges
    if rule_priority >= 67:
        return "urgent"
    if rule_priority >= 34:
        return "normal"
    return "low"


def _priority_to_int(priority: Literal["urgent", "normal", "low"]) -> int:
    """Convert string priority to integer for DB storage."""
    if priority == "urgent":
        return 100
    if priority == "normal":
        return 50
    return 0
