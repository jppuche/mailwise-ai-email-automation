"""Tests for RoutingService — mocked DB session + channel adapter.

Coverage targets:
  - route(): happy path single rule, multiple rules, no matching rules,
    partial failure, all actions fail, VIP sender priority, wrong state, not found
  - _dispatch_rule_actions(): idempotency skip for already-dispatched action
  - _build_routing_context(): missing ClassificationResult, missing ActionCategory,
    missing TypeCategory
  - test_route(): dry-run returns RuleTestResult, no side effects

Mocking strategy:
  - AsyncSession: db.execute is AsyncMock with side_effect list (sequential calls).
    Each DB query in the service is a distinct db.execute() call.
  - ChannelAdapter: AsyncMock, send_notification returns DeliveryResult.
  - Settings: MagicMock with routing_ attributes.
  - Email / ClassificationResult / RoutingRule: MagicMock — SQLAlchemy ORM
    objects require mapper initialization that only happens with a live DB.
    Using __new__ raises AttributeError on InstrumentedAttribute.__set__.
  - RuleEngine: NOT mocked — it is pure local computation (D8). We configure
    rule.conditions / rule.actions so rules match the context we construct.
"""

from __future__ import annotations

import uuid
from datetime import datetime  # noqa: F401  # datetime kept for future use
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.adapters.channel.exceptions import (
    ChannelAuthError,
    ChannelDeliveryError,
    ChannelRateLimitError,
)
from src.adapters.channel.schemas import DeliveryResult
from src.core.exceptions import InvalidStateTransitionError
from src.models.classification import ClassificationConfidence
from src.models.email import EmailState
from src.models.routing import RoutingActionStatus
from src.services.routing import RoutingService
from src.services.schemas.routing import RoutingResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EMAIL_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_RULE_ID_1 = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_RULE_ID_2 = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_ACTION_CAT_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_TYPE_CAT_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

_SENDER = "user@example.com"
_SUBJECT = "Help with order"
_SNIPPET = "I need help with my order #12345"

# ---------------------------------------------------------------------------
# Helpers: mock object factories
# ---------------------------------------------------------------------------


def _make_settings(
    *,
    vip_senders: str = "",
    dashboard_url: str = "http://localhost:3000",
    snippet_length: int = 150,
) -> MagicMock:
    """Build a MagicMock Settings with routing defaults."""
    settings = MagicMock()
    settings.routing_vip_senders = vip_senders
    settings.routing_dashboard_base_url = dashboard_url
    settings.routing_snippet_length = snippet_length
    return settings


def _make_email_mock(
    *,
    email_id: uuid.UUID = _EMAIL_ID,
    state: EmailState = EmailState.CLASSIFIED,
    sender_email: str = _SENDER,
    sender_name: str | None = "Test User",
    subject: str = _SUBJECT,
    snippet: str | None = _SNIPPET,
) -> MagicMock:
    """Build a mock Email with all attributes the service reads.

    transition_to() has a side_effect that mutates mock.state so assertions
    on email.state after routing are meaningful.
    """
    email = MagicMock()
    email.id = email_id
    email.state = state
    email.sender_email = sender_email
    email.sender_name = sender_name
    email.subject = subject
    email.snippet = snippet

    # Make transition_to actually update email.state (mirrors the real method)
    def _transition_to(new_state: EmailState) -> None:
        email.state = new_state

    email.transition_to = MagicMock(side_effect=_transition_to)
    return email


def _make_email_mock_raising(
    *,
    email_id: uuid.UUID = _EMAIL_ID,
    state: EmailState = EmailState.CLASSIFIED,
    sender_email: str = _SENDER,
    sender_name: str | None = "Test User",
    subject: str = _SUBJECT,
    snippet: str | None = _SNIPPET,
) -> MagicMock:
    """Email whose transition_to raises InvalidStateTransitionError for wrong-state tests."""
    email = _make_email_mock(
        email_id=email_id,
        state=state,
        sender_email=sender_email,
        sender_name=sender_name,
        subject=subject,
        snippet=snippet,
    )
    # state != CLASSIFIED so the service raises before calling transition_to
    return email


def _make_cr_mock(
    *,
    email_id: uuid.UUID = _EMAIL_ID,
    action_category_id: uuid.UUID = _ACTION_CAT_ID,
    type_category_id: uuid.UUID = _TYPE_CAT_ID,
    confidence: ClassificationConfidence = ClassificationConfidence.HIGH,
) -> MagicMock:
    """Build a mock ClassificationResult."""
    cr = MagicMock()
    cr.id = uuid.uuid4()
    cr.email_id = email_id
    cr.action_category_id = action_category_id
    cr.type_category_id = type_category_id
    # confidence.value must equal "high" or "low" — use a real enum member
    cr.confidence = confidence
    return cr


def _make_rule_mock(
    *,
    rule_id: uuid.UUID = _RULE_ID_1,
    name: str = "Support to Slack",
    priority: int = 50,
    is_active: bool = True,
    action_slug: str = "reply_needed",
    channel: str = "slack",
    destination: str = "#support",
) -> MagicMock:
    """Build a mock RoutingRule whose conditions match action_category == action_slug."""
    rule = MagicMock()
    rule.id = rule_id
    rule.name = name
    rule.priority = priority
    rule.is_active = is_active
    rule.conditions = [
        {"field": "action_category", "operator": "eq", "value": action_slug}
    ]
    rule.actions = [
        {"channel": channel, "destination": destination, "template_id": None}
    ]
    return rule


def _make_dispatch_mock(
    *,
    status: RoutingActionStatus = RoutingActionStatus.DISPATCHED,
) -> MagicMock:
    """Build a mock RoutingAction (for idempotency check returns)."""
    action = MagicMock()
    action.id = uuid.uuid4()
    action.status = status
    action.dispatch_id = "existing-dispatch-id"
    return action


def _make_delivery_result(
    *,
    success: bool = True,
    message_ts: str | None = "1234567890.123456",
    channel_id: str | None = "C123",
) -> DeliveryResult:
    return DeliveryResult(success=success, message_ts=message_ts, channel_id=channel_id)


def _make_adapter(delivery_result: DeliveryResult | None = None) -> AsyncMock:
    """Build a mock ChannelAdapter."""
    adapter = AsyncMock()
    adapter.send_notification.return_value = (
        delivery_result if delivery_result is not None else _make_delivery_result()
    )
    return adapter


def _make_service(
    *,
    adapters: dict[str, AsyncMock] | None = None,
    settings: MagicMock | None = None,
) -> RoutingService:
    """Build a RoutingService with mocked adapters and settings."""
    if adapters is None:
        adapters = {"slack": _make_adapter()}
    if settings is None:
        settings = _make_settings()
    return RoutingService(
        channel_adapters=adapters,  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# DB mock builder
# ---------------------------------------------------------------------------

def _make_scalar_result(value: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _make_scalars_result(values: list[object]) -> MagicMock:
    r = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = values
    r.scalars.return_value = scalars_mock
    return r


def _make_db(
    *,
    email: MagicMock | None = None,
    cr: MagicMock | None = None,
    action_slug: str = "reply_needed",
    type_slug: str = "customer_support",
    rules: list[MagicMock] | None = None,
    existing_dispatch: MagicMock | None = None,
) -> AsyncMock:
    """Build an AsyncSession mock for a standard route() call sequence.

    The service calls db.execute() in this order during route():
      1. _load_email_or_raise         → .scalar_one_or_none() → Email
      2. _build_routing_context CR    → .scalar_one_or_none() → ClassificationResult
      3. _build_routing_context action → .scalar_one_or_none() → action_slug str
      4. _build_routing_context type  → .scalar_one_or_none() → type_slug str
      5. _load_active_rules           → .scalars().all()       → list[RoutingRule]
      6+. _find_existing_dispatch (one per action across all rules)
    """
    if email is None:
        email = _make_email_mock()
    if cr is None:
        cr = _make_cr_mock()
    if rules is None:
        rules = [_make_rule_mock()]

    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.rollback = AsyncMock()

    side_effects: list[object] = [
        _make_scalar_result(email),          # 1 _load_email_or_raise
        _make_scalar_result(cr),             # 2 ClassificationResult
        _make_scalar_result(action_slug),    # 3 action_slug
        _make_scalar_result(type_slug),      # 4 type_slug
        _make_scalars_result(rules),         # 5 _load_active_rules
    ]
    # 6+: one idempotency check per action across all rules
    for rule in rules:
        for _ in rule.actions:
            side_effects.append(_make_scalar_result(existing_dispatch))

    db.execute.side_effect = side_effects
    return db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def slack_adapter() -> AsyncMock:
    return _make_adapter()


@pytest.fixture()
def service(slack_adapter: AsyncMock) -> RoutingService:
    return _make_service(adapters={"slack": slack_adapter})


# ---------------------------------------------------------------------------
# 1. Happy path: single rule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_happy_path_single_rule(slack_adapter: AsyncMock) -> None:
    """CLASSIFIED email + 1 matching rule → ROUTED, 1 action dispatched."""
    service = _make_service(adapters={"slack": slack_adapter})
    email = _make_email_mock()
    db = _make_db(email=email, rules=[_make_rule_mock()])

    result = await service.route(_EMAIL_ID, db)

    assert isinstance(result, RoutingResult)
    assert result.email_id == _EMAIL_ID
    assert result.rules_matched == 1
    assert result.rules_executed == 1
    assert result.actions_dispatched == 1
    assert result.actions_failed == 0
    assert result.was_routed is True
    assert result.final_state == "ROUTED"
    assert len(result.routing_action_ids) == 1

    # Adapter called once with correct destination
    slack_adapter.send_notification.assert_awaited_once()
    payload = slack_adapter.send_notification.await_args.args[0]
    destination = slack_adapter.send_notification.await_args.args[1]
    assert destination == "#support"
    assert payload.email_id == str(_EMAIL_ID)

    # Email transitioned to ROUTED
    assert email.state == EmailState.ROUTED
    # At least two commits: one for action, one for final state
    assert db.commit.await_count >= 2


# ---------------------------------------------------------------------------
# 2. Multiple matching rules — not first-match-wins
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_multiple_matching_rules(slack_adapter: AsyncMock) -> None:
    """2 matching rules → both executed (not first-match-wins)."""
    rule1 = _make_rule_mock(rule_id=_RULE_ID_1, name="Rule 1", destination="#support")
    rule2 = _make_rule_mock(rule_id=_RULE_ID_2, name="Rule 2", destination="#alerts")
    service = _make_service(adapters={"slack": slack_adapter})
    email = _make_email_mock()
    db = _make_db(email=email, rules=[rule1, rule2])

    result = await service.route(_EMAIL_ID, db)

    assert result.rules_matched == 2
    assert result.rules_executed == 2
    assert result.actions_dispatched == 2
    assert result.actions_failed == 0
    assert result.was_routed is True
    # Adapter called twice
    assert slack_adapter.send_notification.await_count == 2


# ---------------------------------------------------------------------------
# 3. No matching rules → ROUTED (unrouted is valid, not error)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_no_matching_rules_unrouted() -> None:
    """0 rules match → ROUTED (was_routed=True), no adapter calls."""
    # Rule requires "escalate" but context will have "reply_needed"
    non_matching_rule = _make_rule_mock(action_slug="escalate")
    adapter = _make_adapter()
    service = _make_service(adapters={"slack": adapter})
    email = _make_email_mock()
    db = _make_db(email=email, action_slug="reply_needed", rules=[non_matching_rule])

    result = await service.route(_EMAIL_ID, db)

    assert result.rules_matched == 0
    assert result.actions_dispatched == 0
    assert result.was_routed is True
    assert result.final_state == "ROUTED"
    assert email.state == EmailState.ROUTED
    adapter.send_notification.assert_not_awaited()


# ---------------------------------------------------------------------------
# 4. Partial failure: 2 rules, 1 succeeds, 1 fails → ROUTED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_partial_failure() -> None:
    """2 rules: 1 succeeds, 1 adapter fails → ROUTED (dispatched_count > 0)."""
    rule1 = _make_rule_mock(rule_id=_RULE_ID_1, name="Rule OK", destination="#support")
    rule2 = _make_rule_mock(rule_id=_RULE_ID_2, name="Rule Fail", destination="#broken")

    adapter = AsyncMock()
    adapter.send_notification.side_effect = [
        _make_delivery_result(),
        ChannelDeliveryError("channel not found"),
    ]
    service = _make_service(adapters={"slack": adapter})
    email = _make_email_mock()
    db = _make_db(email=email, rules=[rule1, rule2])

    result = await service.route(_EMAIL_ID, db)

    assert result.actions_dispatched == 1
    assert result.actions_failed == 1
    assert result.was_routed is True
    assert result.final_state == "ROUTED"
    assert email.state == EmailState.ROUTED


# ---------------------------------------------------------------------------
# 5. All actions fail → ROUTING_FAILED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_all_actions_fail() -> None:
    """All adapter calls fail → ROUTING_FAILED."""
    adapter = AsyncMock()
    adapter.send_notification.side_effect = ChannelAuthError("token revoked")
    service = _make_service(adapters={"slack": adapter})
    email = _make_email_mock()
    db = _make_db(email=email, rules=[_make_rule_mock()])

    result = await service.route(_EMAIL_ID, db)

    assert result.actions_dispatched == 0
    assert result.actions_failed == 1
    assert result.was_routed is False
    assert result.final_state == "ROUTING_FAILED"
    assert email.state == EmailState.ROUTING_FAILED


# ---------------------------------------------------------------------------
# 6. VIP sender → urgent priority
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_vip_sender_urgent_priority() -> None:
    """VIP sender gets 'urgent' priority in the RoutingPayload."""
    vip_email = "ceo@vip.com"
    settings = _make_settings(vip_senders="ceo@vip.com,cto@vip.com")
    adapter = _make_adapter()
    service = _make_service(adapters={"slack": adapter}, settings=settings)
    email = _make_email_mock(sender_email=vip_email)
    db = _make_db(email=email)

    result = await service.route(_EMAIL_ID, db)

    assert result.was_routed is True
    adapter.send_notification.assert_awaited_once()
    payload = adapter.send_notification.await_args.args[0]
    assert payload.priority == "urgent"


# ---------------------------------------------------------------------------
# 7. Wrong state → InvalidStateTransitionError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_email_not_classified_raises() -> None:
    """Email in FETCHED state raises InvalidStateTransitionError."""
    email = _make_email_mock(state=EmailState.FETCHED)
    db = _make_db(email=email)
    service = _make_service()

    with pytest.raises(InvalidStateTransitionError, match="must be CLASSIFIED"):
        await service.route(_EMAIL_ID, db)

    # State must NOT have been changed
    assert email.state == EmailState.FETCHED
    # DB commit must NOT have been called
    db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# 8. Email not found → ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_email_not_found_raises() -> None:
    """Email not in DB raises ValueError."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.execute.return_value = _make_scalar_result(None)
    service = _make_service()

    with pytest.raises(ValueError, match="not found"):
        await service.route(_EMAIL_ID, db)

    db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# Idempotency: already-dispatched action is skipped (no adapter call)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_idempotency_skips_already_dispatched() -> None:
    """If a RoutingAction with same dispatch_id already DISPATCHED, skip adapter call."""
    existing = _make_dispatch_mock(status=RoutingActionStatus.DISPATCHED)
    adapter = _make_adapter()
    service = _make_service(adapters={"slack": adapter})
    email = _make_email_mock()
    db = _make_db(email=email, existing_dispatch=existing)

    result = await service.route(_EMAIL_ID, db)

    # Idempotent: counted as dispatched
    assert result.actions_dispatched == 1
    assert result.was_routed is True
    # Adapter must NOT have been called
    adapter.send_notification.assert_not_awaited()


# ---------------------------------------------------------------------------
# No adapter registered for channel → records FAILED action, ROUTING_FAILED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_no_adapter_registered_records_failure() -> None:
    """Rule action references 'email' channel but only 'slack' adapter registered."""
    rule = _make_rule_mock(channel="email", destination="support@company.com")
    service = _make_service(adapters={"slack": _make_adapter()})
    email = _make_email_mock()
    db = _make_db(email=email, rules=[rule])

    result = await service.route(_EMAIL_ID, db)

    assert result.actions_dispatched == 0
    assert result.actions_failed == 1
    assert result.was_routed is False
    assert email.state == EmailState.ROUTING_FAILED


# ---------------------------------------------------------------------------
# ChannelRateLimitError → action FAILED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_rate_limit_error_records_failure() -> None:
    """ChannelRateLimitError on adapter is caught → action FAILED, ROUTING_FAILED."""
    adapter = AsyncMock()
    adapter.send_notification.side_effect = ChannelRateLimitError(
        "rate limited", retry_after_seconds=30
    )
    service = _make_service(adapters={"slack": adapter})
    email = _make_email_mock()
    db = _make_db(email=email)

    result = await service.route(_EMAIL_ID, db)

    assert result.actions_dispatched == 0
    assert result.actions_failed == 1
    assert result.was_routed is False


# ---------------------------------------------------------------------------
# Missing ClassificationResult → ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_missing_classification_result_raises() -> None:
    """ClassificationResult not found for email → ValueError."""
    email = _make_email_mock()
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [
        _make_scalar_result(email),   # email found
        _make_scalar_result(None),    # ClassificationResult not found
    ]
    service = _make_service()

    with pytest.raises(ValueError, match="ClassificationResult not found"):
        await service.route(_EMAIL_ID, db)

    db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# Missing ActionCategory slug → ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_missing_action_category_raises() -> None:
    """ActionCategory not found for ClassificationResult → ValueError."""
    email = _make_email_mock()
    cr = _make_cr_mock()
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [
        _make_scalar_result(email),
        _make_scalar_result(cr),
        _make_scalar_result(None),  # action_slug not found
    ]
    service = _make_service()

    with pytest.raises(ValueError, match="ActionCategory.*not found"):
        await service.route(_EMAIL_ID, db)


# ---------------------------------------------------------------------------
# Missing TypeCategory slug → ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_missing_type_category_raises() -> None:
    """TypeCategory not found for ClassificationResult → ValueError."""
    email = _make_email_mock()
    cr = _make_cr_mock()
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [
        _make_scalar_result(email),
        _make_scalar_result(cr),
        _make_scalar_result("reply_needed"),
        _make_scalar_result(None),  # type_slug not found
    ]
    service = _make_service()

    with pytest.raises(ValueError, match="TypeCategory.*not found"):
        await service.route(_EMAIL_ID, db)


# ---------------------------------------------------------------------------
# test_route: dry-run — no adapter calls, no DB writes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_route_dry_run_no_side_effects() -> None:
    """test_route() dry-run: returns RuleTestResult, no adapter calls, no DB writes."""
    from src.services.schemas.routing import RoutingContext, RuleTestResult

    rule = _make_rule_mock()
    adapter = _make_adapter()
    service = _make_service(adapters={"slack": adapter})

    db = AsyncMock()
    db.commit = AsyncMock()
    db.execute.return_value = _make_scalars_result([rule])

    context = RoutingContext(
        email_id=_EMAIL_ID,
        action_slug="reply_needed",
        type_slug="customer_support",
        confidence="high",
        sender_email=_SENDER,
        sender_domain="example.com",
        subject=_SUBJECT,
        snippet=_SNIPPET,
        sender_name="Test User",
    )

    result = await service.test_route(context, db)

    assert isinstance(result, RuleTestResult)
    assert result.dry_run is True
    assert result.total_actions == 1
    assert result.rules_matched[0].rule_id == rule.id
    # No adapter calls
    adapter.send_notification.assert_not_awaited()
    # No DB writes
    db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# Low-confidence classification → confidence "low" in context → rule matches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_low_confidence_context() -> None:
    """Low-confidence ClassificationResult → context.confidence == 'low', rule matches."""
    adapter = _make_adapter()
    service = _make_service(adapters={"slack": adapter})
    email = _make_email_mock()
    cr = _make_cr_mock(confidence=ClassificationConfidence.LOW)

    # Rule matches specifically on confidence == "low"
    rule = _make_rule_mock()
    rule.conditions = [{"field": "confidence", "operator": "eq", "value": "low"}]

    db = _make_db(email=email, cr=cr, rules=[rule])

    result = await service.route(_EMAIL_ID, db)

    assert result.rules_matched == 1
    assert result.actions_dispatched == 1
    assert result.was_routed is True


# ---------------------------------------------------------------------------
# Snippet truncation respects routing_snippet_length
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_snippet_truncated_to_settings_length() -> None:
    """Payload snippet is truncated to settings.routing_snippet_length chars."""
    long_snippet = "A" * 500
    settings = _make_settings(snippet_length=100)
    adapter = _make_adapter()
    service = _make_service(adapters={"slack": adapter}, settings=settings)
    email = _make_email_mock(snippet=long_snippet)
    db = _make_db(email=email)

    await service.route(_EMAIL_ID, db)

    payload = adapter.send_notification.await_args.args[0]
    assert len(payload.snippet) == 100


# ---------------------------------------------------------------------------
# Dashboard link contains email_id and base URL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_dashboard_link_contains_email_id() -> None:
    """RoutingPayload.dashboard_link contains the email_id and base URL."""
    settings = _make_settings(dashboard_url="http://app.mailwise.io")
    adapter = _make_adapter()
    service = _make_service(adapters={"slack": adapter}, settings=settings)
    email = _make_email_mock()
    db = _make_db(email=email)

    await service.route(_EMAIL_ID, db)

    payload = adapter.send_notification.await_args.args[0]
    assert str(_EMAIL_ID) in payload.dashboard_link
    assert payload.dashboard_link.startswith("http://app.mailwise.io")


# ---------------------------------------------------------------------------
# VIP domain wildcard → urgent priority
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_vip_domain_wildcard_urgent_priority() -> None:
    """VIP wildcard domain '*.corp.com' gives urgent priority to sub.corp.com sender."""
    settings = _make_settings(vip_senders="*.corp.com")
    adapter = _make_adapter()
    service = _make_service(adapters={"slack": adapter}, settings=settings)
    email = _make_email_mock(sender_email="alice@sub.corp.com")
    db = _make_db(email=email)

    await service.route(_EMAIL_ID, db)

    payload = adapter.send_notification.await_args.args[0]
    assert payload.priority == "urgent"


# ---------------------------------------------------------------------------
# High rule priority (>=67) → urgent dispatch priority
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_high_priority_rule_urgent_dispatch() -> None:
    """Rule with priority >= 67 → payload priority 'urgent'."""
    rule = _make_rule_mock(priority=80)
    adapter = _make_adapter()
    service = _make_service(adapters={"slack": adapter})
    email = _make_email_mock()
    db = _make_db(email=email, rules=[rule])

    await service.route(_EMAIL_ID, db)

    payload = adapter.send_notification.await_args.args[0]
    assert payload.priority == "urgent"


# ---------------------------------------------------------------------------
# Low rule priority (<34) → low dispatch priority
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_low_priority_rule_low_dispatch() -> None:
    """Rule with priority < 34 → payload priority 'low'."""
    rule = _make_rule_mock(priority=10)
    adapter = _make_adapter()
    service = _make_service(adapters={"slack": adapter})
    email = _make_email_mock()
    db = _make_db(email=email, rules=[rule])

    await service.route(_EMAIL_ID, db)

    payload = adapter.send_notification.await_args.args[0]
    assert payload.priority == "low"


# ---------------------------------------------------------------------------
# Escalate action slug → urgent priority (regardless of rule priority)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_escalate_action_slug_urgent_priority() -> None:
    """action_slug == 'escalate' → payload priority 'urgent' regardless of rule priority."""
    rule = _make_rule_mock(priority=10, action_slug="escalate")
    adapter = _make_adapter()
    service = _make_service(adapters={"slack": adapter})
    email = _make_email_mock()
    db = _make_db(email=email, action_slug="escalate", rules=[rule])

    await service.route(_EMAIL_ID, db)

    payload = adapter.send_notification.await_args.args[0]
    assert payload.priority == "urgent"


# ---------------------------------------------------------------------------
# DB error during idempotency check → action counted as failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_idempotency_db_error_counted_as_failed() -> None:
    """SQLAlchemyError during idempotency check → action failed, routing continues."""
    email = _make_email_mock()
    cr = _make_cr_mock()
    rule = _make_rule_mock()

    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.rollback = AsyncMock()
    db.execute.side_effect = [
        _make_scalar_result(email),
        _make_scalar_result(cr),
        _make_scalar_result("reply_needed"),
        _make_scalar_result("customer_support"),
        _make_scalars_result([rule]),
        SQLAlchemyError("connection timeout"),  # idempotency check fails
    ]

    adapter = _make_adapter()
    service = _make_service(adapters={"slack": adapter})

    result = await service.route(_EMAIL_ID, db)

    assert result.actions_dispatched == 0
    assert result.actions_failed == 1
    assert result.was_routed is False
    adapter.send_notification.assert_not_awaited()


# ---------------------------------------------------------------------------
# Subject keyword escalation → urgent priority
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_urgent_keyword_in_subject_urgent_priority() -> None:
    """'urgent' keyword in subject → payload priority 'urgent' (low rule priority)."""
    rule = _make_rule_mock(priority=10)  # low priority rule
    adapter = _make_adapter()
    service = _make_service(adapters={"slack": adapter})
    email = _make_email_mock(subject="URGENT: system down")
    db = _make_db(email=email, rules=[rule])

    await service.route(_EMAIL_ID, db)

    payload = adapter.send_notification.await_args.args[0]
    assert payload.priority == "urgent"


# ---------------------------------------------------------------------------
# Sender info in payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_sender_info_in_payload() -> None:
    """RoutingPayload.sender reflects email.sender_email and sender_name."""
    adapter = _make_adapter()
    service = _make_service(adapters={"slack": adapter})
    email = _make_email_mock(
        sender_email="alice@example.com",
        sender_name="Alice Smith",
    )
    db = _make_db(email=email)

    await service.route(_EMAIL_ID, db)

    payload = adapter.send_notification.await_args.args[0]
    assert payload.sender.email == "alice@example.com"
    assert payload.sender.name == "Alice Smith"


# ---------------------------------------------------------------------------
# Classification info in payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_classification_info_in_payload() -> None:
    """RoutingPayload.classification reflects action/type/confidence from context."""
    adapter = _make_adapter()
    service = _make_service(adapters={"slack": adapter})
    email = _make_email_mock()
    db = _make_db(
        email=email,
        action_slug="reply_needed",
        type_slug="customer_support",
    )

    await service.route(_EMAIL_ID, db)

    payload = adapter.send_notification.await_args.args[0]
    assert payload.classification.action == "reply_needed"
    assert payload.classification.type == "customer_support"
    assert payload.classification.confidence == "high"
