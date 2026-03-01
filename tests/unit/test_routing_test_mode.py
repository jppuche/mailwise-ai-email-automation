"""Tests for RoutingService.test_route() dry-run method.

GUARANTEE under test: test_route() does NOT:
  - Create any RoutingAction in DB (db.add() never called with RoutingAction)
  - Call any channel adapter's send_notification()
  - Change email state

It DOES:
  - Load rules from DB via _load_active_rules()
  - Evaluate them via RuleEngine
  - Return RuleTestResult with matched rules and would-be dispatches
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.routing import RoutingAction
from src.services.routing import RoutingService
from src.services.schemas.routing import RoutingContext, RuleTestResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(**overrides: Any) -> RoutingContext:
    """Return a minimal valid RoutingContext."""
    defaults: dict[str, Any] = {
        "email_id": uuid.uuid4(),
        "action_slug": "urgent",
        "type_slug": "customer_support",
        "confidence": "high",
        "sender_email": "user@company.com",
        "sender_domain": "company.com",
        "subject": "Test",
        "snippet": "Test snippet",
    }
    defaults.update(overrides)
    return RoutingContext(**defaults)


def _make_settings(**overrides: Any) -> MagicMock:
    """Return a MagicMock settings object with sensible defaults."""
    settings = MagicMock()
    settings.routing_vip_senders = ""
    settings.routing_dashboard_base_url = "http://localhost:3000"
    settings.routing_snippet_length = 150
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def _make_routing_rule(
    *,
    rule_id: uuid.UUID | None = None,
    name: str = "Test Rule",
    priority: int = 50,
    is_active: bool = True,
    conditions: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Return a MagicMock RoutingRule with the given attributes.

    Conditions default to matching the _make_context() defaults:
    action_category eq 'urgent'.
    Actions default to a single slack dispatch.
    """
    rule = MagicMock()
    rule.id = rule_id or uuid.uuid4()
    rule.name = name
    rule.priority = priority
    rule.is_active = is_active
    rule.conditions = conditions if conditions is not None else [
        {"field": "action_category", "operator": "eq", "value": "urgent"}
    ]
    rule.actions = actions if actions is not None else [
        {"channel": "slack", "destination": "#support", "template_id": None}
    ]
    return rule


def _make_service(
    *,
    adapter: AsyncMock | None = None,
    settings: MagicMock | None = None,
) -> tuple[RoutingService, AsyncMock, MagicMock]:
    """Return (service, mock_adapter, mock_settings)."""
    mock_adapter = adapter or AsyncMock()
    mock_settings = settings or _make_settings()
    service = RoutingService(
        channel_adapters={"slack": mock_adapter},
        settings=mock_settings,
    )
    return service, mock_adapter, mock_settings


def _make_db(rules: list[Any]) -> AsyncMock:
    """Return an AsyncMock db session whose execute() yields the given rules."""
    db = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = rules
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    db.execute.return_value = result_mock
    return db


# ---------------------------------------------------------------------------
# Test 1: rules that match the context are returned in result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_returns_matching_rules() -> None:
    """Matched rules are reflected in RuleTestResult.rules_matched."""
    rule = _make_routing_rule(
        name="Support Escalation",
        priority=70,
        conditions=[{"field": "action_category", "operator": "eq", "value": "urgent"}],
    )
    service, _, _ = _make_service()
    db = _make_db([rule])
    context = _make_context(action_slug="urgent")

    result = await service.test_route(context, db)

    assert isinstance(result, RuleTestResult)
    assert len(result.rules_matched) == 1
    assert result.rules_matched[0].rule_name == "Support Escalation"
    assert result.rules_matched[0].priority == 70


# ---------------------------------------------------------------------------
# Test 2: adapter send_notification is never called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_no_adapter_called() -> None:
    """test_route() must never call send_notification() on any channel adapter."""
    rule = _make_routing_rule()
    service, mock_adapter, _ = _make_service()
    db = _make_db([rule])
    context = _make_context(action_slug="urgent")

    await service.test_route(context, db)

    mock_adapter.send_notification.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: db.add() never called with a RoutingAction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_no_routing_action_created() -> None:
    """test_route() must not create RoutingAction rows (db.add() not called)."""
    rule = _make_routing_rule()
    service, _, _ = _make_service()
    db = _make_db([rule])
    context = _make_context(action_slug="urgent")

    await service.test_route(context, db)

    # db.add() must never have been called at all
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_dry_run_no_routing_action_created_checks_type() -> None:
    """Even if db.add() is called for some reason, it must not be for RoutingAction."""
    rule = _make_routing_rule()
    service, _, _ = _make_service()
    db = _make_db([rule])
    context = _make_context(action_slug="urgent")

    await service.test_route(context, db)

    # Confirm no call passed a RoutingAction instance
    for c in db.add.call_args_list:
        args, _ = c
        for arg in args:
            assert not isinstance(arg, RoutingAction), (
                f"db.add() was called with a RoutingAction: {arg!r}"
            )


# ---------------------------------------------------------------------------
# Test 4: email state unchanged (no transition, no commit on email)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_email_state_unchanged() -> None:
    """test_route() does not call db.commit() (no state transition on any email)."""
    rule = _make_routing_rule()
    service, _, _ = _make_service()
    db = _make_db([rule])
    context = _make_context(action_slug="urgent")

    await service.test_route(context, db)

    db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: result.dry_run is True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_flag_is_true() -> None:
    """RuleTestResult.dry_run must always be True."""
    service, _, _ = _make_service()
    db = _make_db([])
    context = _make_context()

    result = await service.test_route(context, db)

    assert result.dry_run is True


@pytest.mark.asyncio
async def test_dry_run_flag_is_true_even_with_matching_rules() -> None:
    """dry_run is True regardless of whether rules matched."""
    rule = _make_routing_rule()
    service, _, _ = _make_service()
    db = _make_db([rule])
    context = _make_context(action_slug="urgent")

    result = await service.test_route(context, db)

    assert result.dry_run is True


# ---------------------------------------------------------------------------
# Test 6: total_actions matches len(would_dispatch)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_would_dispatch_count_single_rule_single_action() -> None:
    """total_actions equals len(would_dispatch) for one rule with one action."""
    rule = _make_routing_rule(
        actions=[{"channel": "slack", "destination": "#ops", "template_id": None}]
    )
    service, _, _ = _make_service()
    db = _make_db([rule])
    context = _make_context(action_slug="urgent")

    result = await service.test_route(context, db)

    assert result.total_actions == len(result.would_dispatch)
    assert result.total_actions == 1


@pytest.mark.asyncio
async def test_dry_run_would_dispatch_count_single_rule_multiple_actions() -> None:
    """total_actions equals len(would_dispatch) for one rule with multiple actions."""
    rule = _make_routing_rule(
        actions=[
            {"channel": "slack", "destination": "#support", "template_id": None},
            {"channel": "slack", "destination": "#escalations", "template_id": "tmpl-vip"},
        ]
    )
    service, _, _ = _make_service()
    db = _make_db([rule])
    context = _make_context(action_slug="urgent")

    result = await service.test_route(context, db)

    assert result.total_actions == len(result.would_dispatch)
    assert result.total_actions == 2


@pytest.mark.asyncio
async def test_dry_run_would_dispatch_count_zero_when_no_match() -> None:
    """total_actions is 0 and would_dispatch is empty when no rule matches."""
    # Rule condition won't match 'urgent' — different action slug
    rule = _make_routing_rule(
        conditions=[{"field": "action_category", "operator": "eq", "value": "archive"}]
    )
    service, _, _ = _make_service()
    db = _make_db([rule])
    context = _make_context(action_slug="urgent")

    result = await service.test_route(context, db)

    assert result.total_actions == len(result.would_dispatch)
    assert result.total_actions == 0


# ---------------------------------------------------------------------------
# Test 7: no matching rules → empty results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_no_matching_rules_when_no_rules_in_db() -> None:
    """Empty rule list → empty result."""
    service, _, _ = _make_service()
    db = _make_db([])
    context = _make_context()

    result = await service.test_route(context, db)

    assert result.rules_matched == []
    assert result.would_dispatch == []
    assert result.total_actions == 0
    assert result.dry_run is True


@pytest.mark.asyncio
async def test_dry_run_no_matching_rules_when_conditions_do_not_match() -> None:
    """Rules exist but none match the context → empty results."""
    rule = _make_routing_rule(
        name="Archive Rule",
        conditions=[{"field": "action_category", "operator": "eq", "value": "archive"}],
    )
    service, _, _ = _make_service()
    db = _make_db([rule])
    context = _make_context(action_slug="urgent")  # Does NOT match "archive"

    result = await service.test_route(context, db)

    assert result.rules_matched == []
    assert result.would_dispatch == []
    assert result.total_actions == 0


@pytest.mark.asyncio
async def test_dry_run_no_matching_rules_inactive_rule_skipped() -> None:
    """Inactive rules are not evaluated by the rule engine."""
    # is_active=False — rule engine skips inactive rules
    rule = _make_routing_rule(
        is_active=False,
        conditions=[{"field": "action_category", "operator": "eq", "value": "urgent"}],
    )
    service, _, _ = _make_service()
    # The DB mock returns the rule as if _load_active_rules filtered it out already
    # (since _load_active_rules uses .where(RoutingRule.is_active.is_(True))).
    # But the rule engine also re-checks is_active for safety. Either way: no match.
    db = _make_db([rule])
    context = _make_context(action_slug="urgent")

    result = await service.test_route(context, db)

    # RuleEngine.evaluate() skips is_active=False rules
    assert result.rules_matched == []
    assert result.total_actions == 0


# ---------------------------------------------------------------------------
# Test 8: multiple matching rules all returned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_multiple_rules_match_all_returned() -> None:
    """All matching rules are present in rules_matched in priority order."""
    rule_a = _make_routing_rule(
        name="High Priority Rule",
        priority=90,
        conditions=[{"field": "action_category", "operator": "eq", "value": "urgent"}],
        actions=[{"channel": "slack", "destination": "#urgent", "template_id": None}],
    )
    rule_b = _make_routing_rule(
        name="Medium Priority Rule",
        priority=50,
        conditions=[{"field": "confidence", "operator": "eq", "value": "high"}],
        actions=[{"channel": "slack", "destination": "#support", "template_id": None}],
    )
    service, _, _ = _make_service()
    # Pass in priority-desc order as _load_active_rules does
    db = _make_db([rule_a, rule_b])
    context = _make_context(action_slug="urgent", confidence="high")

    result = await service.test_route(context, db)

    assert len(result.rules_matched) == 2
    rule_names = [m.rule_name for m in result.rules_matched]
    assert "High Priority Rule" in rule_names
    assert "Medium Priority Rule" in rule_names


@pytest.mark.asyncio
async def test_dry_run_multiple_rules_match_would_dispatch_aggregated() -> None:
    """would_dispatch aggregates actions from ALL matched rules."""
    rule_a = _make_routing_rule(
        name="Rule A",
        priority=80,
        conditions=[{"field": "action_category", "operator": "eq", "value": "urgent"}],
        actions=[{"channel": "slack", "destination": "#urgent", "template_id": None}],
    )
    rule_b = _make_routing_rule(
        name="Rule B",
        priority=40,
        conditions=[{"field": "action_category", "operator": "eq", "value": "urgent"}],
        actions=[
            {"channel": "slack", "destination": "#support", "template_id": None},
            {"channel": "slack", "destination": "#alerts", "template_id": "tmpl-alert"},
        ],
    )
    service, _, _ = _make_service()
    db = _make_db([rule_a, rule_b])
    context = _make_context(action_slug="urgent")

    result = await service.test_route(context, db)

    # Rule A: 1 action + Rule B: 2 actions = 3 total
    assert result.total_actions == 3
    assert len(result.would_dispatch) == 3
    assert result.total_actions == len(result.would_dispatch)


@pytest.mark.asyncio
async def test_dry_run_multiple_rules_partial_match() -> None:
    """Only rules whose conditions match the context appear in rules_matched."""
    matching_rule = _make_routing_rule(
        name="Matching Rule",
        priority=70,
        conditions=[{"field": "action_category", "operator": "eq", "value": "urgent"}],
        actions=[{"channel": "slack", "destination": "#ops", "template_id": None}],
    )
    non_matching_rule = _make_routing_rule(
        name="Non-Matching Rule",
        priority=30,
        conditions=[{"field": "action_category", "operator": "eq", "value": "archive"}],
        actions=[{"channel": "slack", "destination": "#archive", "template_id": None}],
    )
    service, _, _ = _make_service()
    db = _make_db([matching_rule, non_matching_rule])
    context = _make_context(action_slug="urgent")

    result = await service.test_route(context, db)

    assert len(result.rules_matched) == 1
    assert result.rules_matched[0].rule_name == "Matching Rule"
    assert result.total_actions == 1


# ---------------------------------------------------------------------------
# Test: result contains the original context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_result_context_is_input_context() -> None:
    """RuleTestResult.context is the exact RoutingContext passed in."""
    service, _, _ = _make_service()
    db = _make_db([])
    context = _make_context(
        action_slug="forward",
        type_slug="inquiry",
        sender_email="alice@corp.com",
    )

    result = await service.test_route(context, db)

    assert result.context.email_id == context.email_id
    assert result.context.action_slug == "forward"
    assert result.context.type_slug == "inquiry"
    assert result.context.sender_email == "alice@corp.com"


# ---------------------------------------------------------------------------
# Test: would_dispatch action definitions are correct
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_would_dispatch_action_definitions() -> None:
    """RoutingActionDef in would_dispatch matches the rule's action definition."""
    rule = _make_routing_rule(
        actions=[
            {"channel": "slack", "destination": "#vip", "template_id": "tmpl-vip"}
        ]
    )
    service, _, _ = _make_service()
    db = _make_db([rule])
    context = _make_context(action_slug="urgent")

    result = await service.test_route(context, db)

    assert len(result.would_dispatch) == 1
    action_def = result.would_dispatch[0]
    assert action_def.channel == "slack"
    assert action_def.destination == "#vip"
    assert action_def.template_id == "tmpl-vip"


# ---------------------------------------------------------------------------
# Test: db.execute() called once (for _load_active_rules)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_db_execute_called_once_for_rule_load() -> None:
    """test_route() calls db.execute() exactly once to load active rules."""
    service, _, _ = _make_service()
    db = _make_db([])
    context = _make_context()

    await service.test_route(context, db)

    assert db.execute.call_count == 1


# ---------------------------------------------------------------------------
# Test: no rollback called (no DB writes attempted)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_no_rollback_called() -> None:
    """No db.rollback() since no writes are attempted."""
    rule = _make_routing_rule()
    service, _, _ = _make_service()
    db = _make_db([rule])
    context = _make_context(action_slug="urgent")

    await service.test_route(context, db)

    db.rollback.assert_not_called()
