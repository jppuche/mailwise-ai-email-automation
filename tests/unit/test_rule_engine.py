"""Tests for RuleEngine in src/services/rule_engine.py.

Pure local computation — no external I/O, no try/except, no DB.
All tests are synchronous.

Coverage targets:
  - evaluate: happy path, inactive rule exclusion, empty rules list,
    multi-rule match, priority-order preservation, empty conditions
  - _condition_matches: all six operators, unknown field, unknown operator
  - _apply_operator: eq, contains, in, not_in, starts_with, matches_domain
  - _matches_domain: wildcard match, wildcard no-match on exact, exact match
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.services.rule_engine import RuleEngine
from src.services.schemas.routing import RoutingContext, RuleMatchResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule(
    *,
    rule_id: uuid.UUID | None = None,
    name: str = "Test Rule",
    priority: int = 10,
    is_active: bool = True,
    conditions: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Return a MagicMock that quacks like a RoutingRule ORM model."""
    rule = MagicMock()
    rule.id = rule_id or uuid.uuid4()
    rule.name = name
    rule.priority = priority
    rule.is_active = is_active
    rule.conditions = conditions if conditions is not None else []
    rule.actions = (
        actions
        if actions is not None
        else [{"channel": "slack", "destination": "#general", "template_id": None}]
    )
    return rule


def _make_context(
    *,
    email_id: uuid.UUID | None = None,
    action_slug: str = "reply_needed",
    type_slug: str = "customer_support",
    confidence: str = "high",
    sender_email: str = "sender@example.com",
    sender_domain: str = "example.com",
    subject: str = "Hello from example",
    snippet: str = "Short snippet.",
    sender_name: str | None = None,
) -> RoutingContext:
    """Return a RoutingContext with sensible defaults."""
    return RoutingContext(
        email_id=email_id or uuid.uuid4(),
        action_slug=action_slug,
        type_slug=type_slug,
        confidence=confidence,  # type: ignore[arg-type]
        sender_email=sender_email,
        sender_domain=sender_domain,
        subject=subject,
        snippet=snippet,
        sender_name=sender_name,
    )


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine() -> RuleEngine:
    return RuleEngine()


# ---------------------------------------------------------------------------
# EQ operator
# ---------------------------------------------------------------------------


class TestEqOperator:
    def test_eq_operator_match(self, engine: RuleEngine) -> None:
        context = _make_context(action_slug="urgent")
        rule = _make_rule(
            conditions=[{"field": "action_category", "operator": "eq", "value": "urgent"}]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1
        assert results[0].rule_id == rule.id

    def test_eq_operator_case_insensitive(self, engine: RuleEngine) -> None:
        context = _make_context(action_slug="urgent")
        rule = _make_rule(
            conditions=[{"field": "action_category", "operator": "eq", "value": "Urgent"}]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1

    def test_eq_operator_no_match(self, engine: RuleEngine) -> None:
        context = _make_context(action_slug="urgent")
        rule = _make_rule(
            conditions=[
                {
                    "field": "action_category",
                    "operator": "eq",
                    "value": "reply_needed",
                }
            ]
        )
        results = engine.evaluate(context, [rule])
        assert results == []


# ---------------------------------------------------------------------------
# CONTAINS operator
# ---------------------------------------------------------------------------


class TestContainsOperator:
    def test_contains_operator_match(self, engine: RuleEngine) -> None:
        context = _make_context(subject="Re: Invoice #123")
        rule = _make_rule(
            conditions=[{"field": "subject", "operator": "contains", "value": "invoice"}]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1

    def test_contains_operator_case_insensitive(self, engine: RuleEngine) -> None:
        context = _make_context(subject="invoice details for Q4")
        rule = _make_rule(
            conditions=[{"field": "subject", "operator": "contains", "value": "INVOICE"}]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1

    def test_contains_operator_no_match(self, engine: RuleEngine) -> None:
        context = _make_context(subject="Meeting tomorrow")
        rule = _make_rule(
            conditions=[{"field": "subject", "operator": "contains", "value": "invoice"}]
        )
        results = engine.evaluate(context, [rule])
        assert results == []


# ---------------------------------------------------------------------------
# IN operator
# ---------------------------------------------------------------------------


class TestInOperator:
    def test_in_operator_match(self, engine: RuleEngine) -> None:
        context = _make_context(sender_domain="company.com")
        rule = _make_rule(
            conditions=[
                {
                    "field": "sender_domain",
                    "operator": "in",
                    "value": ["company.com", "partner.com"],
                }
            ]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1

    def test_in_operator_no_match(self, engine: RuleEngine) -> None:
        context = _make_context(sender_domain="company.com")
        rule = _make_rule(
            conditions=[{"field": "sender_domain", "operator": "in", "value": ["other.com"]}]
        )
        results = engine.evaluate(context, [rule])
        assert results == []

    def test_in_operator_case_insensitive(self, engine: RuleEngine) -> None:
        context = _make_context(sender_domain="Company.com")
        rule = _make_rule(
            conditions=[
                {
                    "field": "sender_domain",
                    "operator": "in",
                    "value": ["company.com"],
                }
            ]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1

    def test_in_operator_non_list_value_no_match(self, engine: RuleEngine) -> None:
        # If value is not a list, in-operator returns False.
        context = _make_context(sender_domain="company.com")
        rule = _make_rule(
            conditions=[
                {
                    "field": "sender_domain",
                    "operator": "in",
                    "value": "company.com",
                }
            ]
        )
        results = engine.evaluate(context, [rule])
        assert results == []


# ---------------------------------------------------------------------------
# NOT_IN operator
# ---------------------------------------------------------------------------


class TestNotInOperator:
    def test_not_in_operator_match(self, engine: RuleEngine) -> None:
        context = _make_context(type_slug="customer_support")
        rule = _make_rule(
            conditions=[{"field": "type_category", "operator": "not_in", "value": ["spam"]}]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1

    def test_not_in_operator_no_match(self, engine: RuleEngine) -> None:
        context = _make_context(type_slug="customer_support")
        rule = _make_rule(
            conditions=[
                {
                    "field": "type_category",
                    "operator": "not_in",
                    "value": ["customer_support"],
                }
            ]
        )
        results = engine.evaluate(context, [rule])
        assert results == []

    def test_not_in_operator_case_insensitive(self, engine: RuleEngine) -> None:
        context = _make_context(type_slug="SPAM")
        rule = _make_rule(
            conditions=[{"field": "type_category", "operator": "not_in", "value": ["spam"]}]
        )
        results = engine.evaluate(context, [rule])
        assert results == []

    def test_not_in_operator_non_list_value_matches(self, engine: RuleEngine) -> None:
        # If value is not a list, not_in returns True (everything is "not in" a scalar).
        context = _make_context(type_slug="customer_support")
        rule = _make_rule(
            conditions=[
                {
                    "field": "type_category",
                    "operator": "not_in",
                    "value": "customer_support",
                }
            ]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1


# ---------------------------------------------------------------------------
# STARTS_WITH operator
# ---------------------------------------------------------------------------


class TestStartsWithOperator:
    def test_starts_with_operator_match(self, engine: RuleEngine) -> None:
        context = _make_context(sender_email="ceo@company.com")
        rule = _make_rule(
            conditions=[{"field": "sender_email", "operator": "starts_with", "value": "ceo@"}]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1

    def test_starts_with_operator_no_match(self, engine: RuleEngine) -> None:
        context = _make_context(sender_email="support@company.com")
        rule = _make_rule(
            conditions=[{"field": "sender_email", "operator": "starts_with", "value": "ceo@"}]
        )
        results = engine.evaluate(context, [rule])
        assert results == []

    def test_starts_with_operator_case_insensitive(self, engine: RuleEngine) -> None:
        context = _make_context(sender_email="CEO@COMPANY.COM")
        rule = _make_rule(
            conditions=[{"field": "sender_email", "operator": "starts_with", "value": "ceo@"}]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1


# ---------------------------------------------------------------------------
# MATCHES_DOMAIN operator
# ---------------------------------------------------------------------------


class TestMatchesDomainOperator:
    def test_matches_domain_wildcard(self, engine: RuleEngine) -> None:
        context = _make_context(sender_domain="sub.company.com")
        rule = _make_rule(
            conditions=[
                {
                    "field": "sender_domain",
                    "operator": "matches_domain",
                    "value": "*.company.com",
                }
            ]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1

    def test_matches_domain_wildcard_no_match_exact(self, engine: RuleEngine) -> None:
        # "*.company.com" must NOT match the bare "company.com" domain.
        context = _make_context(sender_domain="company.com")
        rule = _make_rule(
            conditions=[
                {
                    "field": "sender_domain",
                    "operator": "matches_domain",
                    "value": "*.company.com",
                }
            ]
        )
        results = engine.evaluate(context, [rule])
        assert results == []

    def test_matches_domain_exact(self, engine: RuleEngine) -> None:
        context = _make_context(sender_domain="company.com")
        rule = _make_rule(
            conditions=[
                {
                    "field": "sender_domain",
                    "operator": "matches_domain",
                    "value": "company.com",
                }
            ]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1

    def test_matches_domain_exact_no_match(self, engine: RuleEngine) -> None:
        context = _make_context(sender_domain="other.com")
        rule = _make_rule(
            conditions=[
                {
                    "field": "sender_domain",
                    "operator": "matches_domain",
                    "value": "company.com",
                }
            ]
        )
        results = engine.evaluate(context, [rule])
        assert results == []

    def test_matches_domain_wildcard_case_insensitive(self, engine: RuleEngine) -> None:
        context = _make_context(sender_domain="Sub.Company.Com")
        rule = _make_rule(
            conditions=[
                {
                    "field": "sender_domain",
                    "operator": "matches_domain",
                    "value": "*.company.com",
                }
            ]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1


# ---------------------------------------------------------------------------
# AND logic (multiple conditions)
# ---------------------------------------------------------------------------


class TestMultipleConditionsAndLogic:
    def test_multiple_conditions_and_logic_all_match(self, engine: RuleEngine) -> None:
        context = _make_context(action_slug="urgent", sender_domain="company.com")
        rule = _make_rule(
            conditions=[
                {"field": "action_category", "operator": "eq", "value": "urgent"},
                {"field": "sender_domain", "operator": "eq", "value": "company.com"},
            ]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1

    def test_multiple_conditions_and_logic_one_fails(self, engine: RuleEngine) -> None:
        context = _make_context(action_slug="urgent", sender_domain="other.com")
        rule = _make_rule(
            conditions=[
                {"field": "action_category", "operator": "eq", "value": "urgent"},
                {"field": "sender_domain", "operator": "eq", "value": "company.com"},
            ]
        )
        results = engine.evaluate(context, [rule])
        assert results == []

    def test_multiple_conditions_and_logic_both_fail(self, engine: RuleEngine) -> None:
        context = _make_context(action_slug="reply_needed", sender_domain="other.com")
        rule = _make_rule(
            conditions=[
                {"field": "action_category", "operator": "eq", "value": "urgent"},
                {"field": "sender_domain", "operator": "eq", "value": "company.com"},
            ]
        )
        results = engine.evaluate(context, [rule])
        assert results == []


# ---------------------------------------------------------------------------
# Inactive rules
# ---------------------------------------------------------------------------


class TestInactiveRule:
    def test_inactive_rule_excluded(self, engine: RuleEngine) -> None:
        context = _make_context(action_slug="urgent")
        rule = _make_rule(
            is_active=False,
            conditions=[{"field": "action_category", "operator": "eq", "value": "urgent"}],
        )
        results = engine.evaluate(context, [rule])
        assert results == []

    def test_active_and_inactive_mixed(self, engine: RuleEngine) -> None:
        context = _make_context(action_slug="urgent")
        cond = [{"field": "action_category", "operator": "eq", "value": "urgent"}]
        active_rule = _make_rule(name="Active", is_active=True, conditions=cond)
        inactive_rule = _make_rule(name="Inactive", is_active=False, conditions=cond)
        results = engine.evaluate(context, [active_rule, inactive_rule])
        assert len(results) == 1
        assert results[0].rule_name == "Active"


# ---------------------------------------------------------------------------
# Malformed conditions
# ---------------------------------------------------------------------------


class TestMalformedConditions:
    def test_unknown_field_treated_as_no_match(self, engine: RuleEngine) -> None:
        context = _make_context()
        rule = _make_rule(
            conditions=[{"field": "nonexistent_field", "operator": "eq", "value": "anything"}]
        )
        results = engine.evaluate(context, [rule])
        assert results == []

    def test_unknown_operator_treated_as_no_match(self, engine: RuleEngine) -> None:
        context = _make_context(action_slug="urgent")
        rule = _make_rule(
            conditions=[
                {
                    "field": "action_category",
                    "operator": "regex",
                    "value": ".*urgent.*",
                }
            ]
        )
        results = engine.evaluate(context, [rule])
        assert results == []

    def test_malformed_condition_does_not_affect_other_rules(self, engine: RuleEngine) -> None:
        context = _make_context(action_slug="urgent")
        bad_rule = _make_rule(
            name="Bad",
            conditions=[{"field": "bad_field", "operator": "eq", "value": "urgent"}],
        )
        good_rule = _make_rule(
            name="Good",
            conditions=[{"field": "action_category", "operator": "eq", "value": "urgent"}],
        )
        results = engine.evaluate(context, [bad_rule, good_rule])
        assert len(results) == 1
        assert results[0].rule_name == "Good"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_rules_list(self, engine: RuleEngine) -> None:
        context = _make_context()
        results = engine.evaluate(context, [])
        assert results == []
        assert isinstance(results, list)

    def test_priority_order_preserved(self, engine: RuleEngine) -> None:
        context = _make_context(action_slug="urgent")
        condition = [{"field": "action_category", "operator": "eq", "value": "urgent"}]
        rule_low = _make_rule(name="Low", priority=30, conditions=condition)
        rule_high = _make_rule(name="High", priority=10, conditions=condition)
        rule_mid = _make_rule(name="Mid", priority=20, conditions=condition)
        # Pass in order: low, high, mid. Output order must match input, not priority.
        results = engine.evaluate(context, [rule_low, rule_high, rule_mid])
        assert len(results) == 3
        assert [r.rule_name for r in results] == ["Low", "High", "Mid"]

    def test_multiple_rules_match_all_returned(self, engine: RuleEngine) -> None:
        context = _make_context(action_slug="urgent")
        condition = [{"field": "action_category", "operator": "eq", "value": "urgent"}]
        rule_a = _make_rule(name="RuleA", conditions=condition)
        rule_b = _make_rule(name="RuleB", conditions=condition)
        rule_c = _make_rule(name="RuleC", conditions=condition)
        results = engine.evaluate(context, [rule_a, rule_b, rule_c])
        assert len(results) == 3
        names = {r.rule_name for r in results}
        assert names == {"RuleA", "RuleB", "RuleC"}

    def test_rule_with_empty_conditions_matches_all(self, engine: RuleEngine) -> None:
        # No conditions = AND of nothing = vacuously True; rule fires for every context.
        context = _make_context()
        rule = _make_rule(conditions=[])
        results = engine.evaluate(context, [rule])
        assert len(results) == 1

    def test_rule_with_empty_conditions_matches_any_context(self, engine: RuleEngine) -> None:
        for slug in ("urgent", "reply_needed", "archive"):
            context = _make_context(action_slug=slug)
            rule = _make_rule(conditions=[])
            results = engine.evaluate(context, [rule])
            assert len(results) == 1, f"Expected match for action_slug={slug!r}"


# ---------------------------------------------------------------------------
# RuleMatchResult shape
# ---------------------------------------------------------------------------


class TestRuleMatchResultShape:
    def test_match_result_contains_rule_id(self, engine: RuleEngine) -> None:
        rule_id = uuid.uuid4()
        context = _make_context(action_slug="urgent")
        rule = _make_rule(
            rule_id=rule_id,
            conditions=[{"field": "action_category", "operator": "eq", "value": "urgent"}],
        )
        results = engine.evaluate(context, [rule])
        assert results[0].rule_id == rule_id

    def test_match_result_is_rule_match_result_instance(self, engine: RuleEngine) -> None:
        context = _make_context(action_slug="urgent")
        rule = _make_rule(
            conditions=[{"field": "action_category", "operator": "eq", "value": "urgent"}]
        )
        results = engine.evaluate(context, [rule])
        assert isinstance(results[0], RuleMatchResult)

    def test_match_result_actions_mapped_correctly(self, engine: RuleEngine) -> None:
        context = _make_context(action_slug="urgent")
        rule = _make_rule(
            conditions=[{"field": "action_category", "operator": "eq", "value": "urgent"}],
            actions=[
                {"channel": "slack", "destination": "#alerts", "template_id": "tpl-001"},
                {"channel": "email", "destination": "team@corp.com"},
            ],
        )
        results = engine.evaluate(context, [rule])
        assert len(results[0].actions) == 2
        slack_action = results[0].actions[0]
        assert slack_action.channel == "slack"
        assert slack_action.destination == "#alerts"
        assert slack_action.template_id == "tpl-001"
        email_action = results[0].actions[1]
        assert email_action.channel == "email"
        assert email_action.destination == "team@corp.com"
        assert email_action.template_id is None

    def test_match_result_priority_preserved(self, engine: RuleEngine) -> None:
        context = _make_context(action_slug="urgent")
        rule = _make_rule(
            priority=42,
            conditions=[{"field": "action_category", "operator": "eq", "value": "urgent"}],
        )
        results = engine.evaluate(context, [rule])
        assert results[0].priority == 42


# ---------------------------------------------------------------------------
# All ConditionField values are reachable
# ---------------------------------------------------------------------------


class TestAllConditionFields:
    def test_type_category_field(self, engine: RuleEngine) -> None:
        context = _make_context(type_slug="spam")
        rule = _make_rule(
            conditions=[{"field": "type_category", "operator": "eq", "value": "spam"}]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1

    def test_sender_domain_field(self, engine: RuleEngine) -> None:
        context = _make_context(sender_domain="example.com")
        rule = _make_rule(
            conditions=[{"field": "sender_domain", "operator": "eq", "value": "example.com"}]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1

    def test_sender_email_field(self, engine: RuleEngine) -> None:
        context = _make_context(sender_email="alice@example.com")
        rule = _make_rule(
            conditions=[
                {
                    "field": "sender_email",
                    "operator": "eq",
                    "value": "alice@example.com",
                }
            ]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1

    def test_subject_field(self, engine: RuleEngine) -> None:
        context = _make_context(subject="Quarterly Report")
        rule = _make_rule(
            conditions=[{"field": "subject", "operator": "contains", "value": "quarterly"}]
        )
        results = engine.evaluate(context, [rule])
        assert len(results) == 1

    def test_confidence_field(self, engine: RuleEngine) -> None:
        context = _make_context(confidence="low")
        rule = _make_rule(conditions=[{"field": "confidence", "operator": "eq", "value": "low"}])
        results = engine.evaluate(context, [rule])
        assert len(results) == 1
