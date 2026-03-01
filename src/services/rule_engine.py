"""Rule engine — evaluates routing conditions against a RoutingContext.

Pure local computation: no I/O, no DB, no adapter calls.
0 try/except blocks (enforced by grep in exit conditions).
0 adapter imports (enforced by grep in exit conditions).

contract-docstrings:
  Invariants: Only evaluates active rules. Preserves input priority order.
  Guarantees: Returns list (may be empty); never raises.
  Errors raised: None.
  Errors silenced: Malformed conditions (unknown field/operator) → warning + no-match.
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

import structlog

from src.services.schemas.routing import RoutingActionDef, RoutingContext, RuleMatchResult

if TYPE_CHECKING:
    from src.models.routing import RoutingConditions, RoutingRule

logger = structlog.get_logger(__name__)


class ConditionOperator(enum.StrEnum):
    """Supported comparison operators for routing conditions."""

    EQ = "eq"
    CONTAINS = "contains"
    IN = "in"
    NOT_IN = "not_in"
    STARTS_WITH = "starts_with"
    MATCHES_DOMAIN = "matches_domain"


class ConditionField(enum.StrEnum):
    """Evaluable fields from RoutingContext."""

    ACTION_CATEGORY = "action_category"
    TYPE_CATEGORY = "type_category"
    SENDER_DOMAIN = "sender_domain"
    SENDER_EMAIL = "sender_email"
    SUBJECT = "subject"
    CONFIDENCE = "confidence"


_FIELD_TO_ATTR: dict[str, str] = {
    ConditionField.ACTION_CATEGORY.value: "action_slug",
    ConditionField.TYPE_CATEGORY.value: "type_slug",
    ConditionField.SENDER_DOMAIN.value: "sender_domain",
    ConditionField.SENDER_EMAIL.value: "sender_email",
    ConditionField.SUBJECT.value: "subject",
    ConditionField.CONFIDENCE.value: "confidence",
}

_VALID_OPERATORS: frozenset[str] = frozenset(op.value for op in ConditionOperator)
_VALID_FIELDS: frozenset[str] = frozenset(f.value for f in ConditionField)


class RuleEngine:
    """Evaluates routing conditions — pure local computation, no I/O.

    Takes ONLY service-layer schemas (RoutingContext) and ORM models (RoutingRule).
    Does NOT call any adapter. Does NOT write to DB.

    Invariants:
      - Only evaluates rules with is_active=True.
      - Returns results in the same priority order as input.
      - Malformed conditions (unknown field/operator): log warning, treat as no-match.

    Guarantees:
      - Returns list (may be empty); never raises.

    Errors raised: None.
    Errors silenced: Malformed conditions → warning + no-match.
    """

    def evaluate(
        self,
        context: RoutingContext,
        rules: list[RoutingRule],
    ) -> list[RuleMatchResult]:
        """Evaluate all active rules against the context.

        Invariants:
          - Only evaluates rules with is_active=True.
          - Returns results in the same priority order as input.
          - Malformed conditions: log warning, treated as no-match.

        Guarantees:
          - Returns list (may be empty); never raises.

        Errors raised: None.
        Errors silenced: Malformed conditions.
        """
        results: list[RuleMatchResult] = []
        for rule in rules:
            if not rule.is_active:
                continue
            if self._rule_matches(context, rule):
                results.append(
                    RuleMatchResult(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        priority=rule.priority,
                        actions=[
                            RoutingActionDef(
                                channel=a["channel"],
                                destination=a["destination"],
                                template_id=a.get("template_id"),
                            )
                            for a in rule.actions
                        ],
                    )
                )
        return results

    def _rule_matches(self, context: RoutingContext, rule: RoutingRule) -> bool:
        """All conditions must match (AND logic)."""
        return all(self._condition_matches(context, condition) for condition in rule.conditions)

    def _condition_matches(
        self,
        context: RoutingContext,
        condition: RoutingConditions,
    ) -> bool:
        """Evaluate a single condition. Malformed → False + warning."""
        field = condition.get("field", "")
        operator = condition.get("operator", "")
        value = condition.get("value", "")

        if field not in _VALID_FIELDS:
            logger.warning("unknown_condition_field", field=field)
            return False
        if operator not in _VALID_OPERATORS:
            logger.warning("unknown_condition_operator", operator=operator)
            return False

        context_value = self._get_context_value(context, field)
        return self._apply_operator(context_value, operator, value)

    def _get_context_value(self, context: RoutingContext, field: str) -> str:
        """Extract the context value for a given field."""
        attr = _FIELD_TO_ATTR.get(field, "")
        return str(getattr(context, attr, ""))

    def _apply_operator(
        self,
        context_value: str,
        operator: str,
        value: str | list[str],
    ) -> bool:
        """Apply operator logic. All string comparisons are case-insensitive."""
        if operator == ConditionOperator.EQ.value:
            return context_value.lower() == str(value).lower()

        if operator == ConditionOperator.CONTAINS.value:
            return str(value).lower() in context_value.lower()

        if operator == ConditionOperator.IN.value:
            if not isinstance(value, list):
                return False
            return context_value.lower() in [v.lower() for v in value]

        if operator == ConditionOperator.NOT_IN.value:
            if not isinstance(value, list):
                return True
            return context_value.lower() not in [v.lower() for v in value]

        if operator == ConditionOperator.STARTS_WITH.value:
            return context_value.lower().startswith(str(value).lower())

        if operator == ConditionOperator.MATCHES_DOMAIN.value:
            return _matches_domain(context_value, str(value))

        return False


def _matches_domain(context_domain: str, pattern: str) -> bool:
    """Match domain with wildcard support.

    ``"*.company.com"`` matches ``"sub.company.com"`` but NOT ``"company.com"``.
    Exact match (no wildcard): case-insensitive equality.
    """
    context_lower = context_domain.lower()
    pattern_lower = pattern.lower()

    if pattern_lower.startswith("*."):
        suffix = pattern_lower[1:]  # ".company.com"
        return context_lower.endswith(suffix) and context_lower != suffix.lstrip(".")

    return context_lower == pattern_lower
