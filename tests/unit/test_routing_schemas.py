"""Tests for routing service schemas.

Covers: RoutingContext, RoutingRequest, RoutingActionDef,
RuleMatchResult, RoutingResult, RuleTestResult.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from src.services.schemas.routing import (
    RoutingActionDef,
    RoutingContext,
    RoutingRequest,
    RoutingResult,
    RuleMatchResult,
    RuleTestResult,
)


# ---------------------------------------------------------------------------
# RoutingContext
# ---------------------------------------------------------------------------


class TestRoutingContext:
    def _valid_payload(self, **overrides: object) -> dict[str, object]:
        defaults: dict[str, object] = {
            "email_id": uuid.uuid4(),
            "action_slug": "reply",
            "type_slug": "complaint",
            "confidence": "high",
            "sender_email": "customer@example.com",
            "sender_domain": "example.com",
            "subject": "Invoice problem",
            "snippet": "I have not received my invoice yet.",
        }
        defaults.update(overrides)
        return defaults

    def test_routing_context_valid(self) -> None:
        email_id = uuid.uuid4()
        ctx = RoutingContext(
            email_id=email_id,
            action_slug="reply",
            type_slug="complaint",
            confidence="high",
            sender_email="customer@example.com",
            sender_domain="example.com",
            subject="Invoice problem",
            snippet="I have not received my invoice yet.",
        )
        assert ctx.email_id == email_id
        assert ctx.action_slug == "reply"
        assert ctx.type_slug == "complaint"
        assert ctx.confidence == "high"
        assert ctx.sender_email == "customer@example.com"
        assert ctx.sender_domain == "example.com"
        assert ctx.subject == "Invoice problem"
        assert ctx.snippet == "I have not received my invoice yet."
        assert ctx.sender_name is None

    def test_routing_context_confidence_high(self) -> None:
        ctx = RoutingContext(**self._valid_payload(confidence="high"))  # type: ignore[arg-type]
        assert ctx.confidence == "high"

    def test_routing_context_confidence_low(self) -> None:
        ctx = RoutingContext(**self._valid_payload(confidence="low"))  # type: ignore[arg-type]
        assert ctx.confidence == "low"

    def test_routing_context_confidence_invalid_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            RoutingContext(**self._valid_payload(confidence="medium"))  # type: ignore[arg-type]
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("confidence",) for e in errors)

    def test_routing_context_confidence_uppercase_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            RoutingContext(**self._valid_payload(confidence="HIGH"))  # type: ignore[arg-type]
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("confidence",) for e in errors)

    def test_routing_context_sender_name_optional_none_by_default(self) -> None:
        ctx = RoutingContext(**self._valid_payload())  # type: ignore[arg-type]
        assert ctx.sender_name is None

    def test_routing_context_sender_name_provided(self) -> None:
        ctx = RoutingContext(
            **self._valid_payload(sender_name="Alice Smith")  # type: ignore[arg-type]
        )
        assert ctx.sender_name == "Alice Smith"

    def test_routing_context_email_id_is_uuid(self) -> None:
        email_id = uuid.uuid4()
        ctx = RoutingContext(**self._valid_payload(email_id=email_id))  # type: ignore[arg-type]
        assert isinstance(ctx.email_id, uuid.UUID)
        assert ctx.email_id == email_id

    def test_routing_context_missing_required_field_raises(self) -> None:
        payload = self._valid_payload()
        del payload["action_slug"]
        with pytest.raises(ValidationError):
            RoutingContext(**payload)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# RoutingRequest
# ---------------------------------------------------------------------------


class TestRoutingRequest:
    def test_routing_request_valid(self) -> None:
        email_id = uuid.uuid4()
        req = RoutingRequest(email_id=email_id)
        assert req.email_id == email_id

    def test_routing_request_email_id_is_uuid(self) -> None:
        req = RoutingRequest(email_id=uuid.uuid4())
        assert isinstance(req.email_id, uuid.UUID)

    def test_routing_request_missing_email_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            RoutingRequest()  # type: ignore[call-arg]

    def test_routing_request_string_uuid_coerced(self) -> None:
        raw_id = uuid.uuid4()
        req = RoutingRequest(email_id=str(raw_id))  # type: ignore[arg-type]
        assert req.email_id == raw_id


# ---------------------------------------------------------------------------
# RoutingActionDef
# ---------------------------------------------------------------------------


class TestRoutingActionDef:
    def test_routing_action_def_valid(self) -> None:
        action = RoutingActionDef(
            channel="slack",
            destination="#support",
        )
        assert action.channel == "slack"
        assert action.destination == "#support"
        assert action.template_id is None

    def test_routing_action_def_template_id_optional(self) -> None:
        action = RoutingActionDef(channel="email", destination="team@example.com")
        assert action.template_id is None

    def test_routing_action_def_template_id_provided(self) -> None:
        action = RoutingActionDef(
            channel="slack",
            destination="#billing",
            template_id="tmpl-001",
        )
        assert action.template_id == "tmpl-001"

    def test_routing_action_def_missing_channel_raises(self) -> None:
        with pytest.raises(ValidationError):
            RoutingActionDef(destination="#support")  # type: ignore[call-arg]

    def test_routing_action_def_missing_destination_raises(self) -> None:
        with pytest.raises(ValidationError):
            RoutingActionDef(channel="slack")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# RuleMatchResult
# ---------------------------------------------------------------------------


class TestRuleMatchResult:
    def _make_action(self, channel: str = "slack", destination: str = "#support") -> RoutingActionDef:
        return RoutingActionDef(channel=channel, destination=destination)

    def test_rule_match_result_valid_with_actions(self) -> None:
        rule_id = uuid.uuid4()
        actions = [self._make_action(), self._make_action(channel="email", destination="ops@example.com")]
        match = RuleMatchResult(
            rule_id=rule_id,
            rule_name="VIP Escalation",
            priority=1,
            actions=actions,
        )
        assert match.rule_id == rule_id
        assert match.rule_name == "VIP Escalation"
        assert match.priority == 1
        assert len(match.actions) == 2
        assert match.actions[0].channel == "slack"
        assert match.actions[1].channel == "email"

    def test_rule_match_result_empty_actions_list(self) -> None:
        match = RuleMatchResult(
            rule_id=uuid.uuid4(),
            rule_name="Catch-all",
            priority=99,
            actions=[],
        )
        assert match.actions == []

    def test_rule_match_result_nested_action_def_structure(self) -> None:
        action = RoutingActionDef(
            channel="slack",
            destination="#alerts",
            template_id="tmpl-urgent",
        )
        match = RuleMatchResult(
            rule_id=uuid.uuid4(),
            rule_name="Urgent Rule",
            priority=0,
            actions=[action],
        )
        assert match.actions[0].template_id == "tmpl-urgent"

    def test_rule_match_result_rule_id_is_uuid(self) -> None:
        rule_id = uuid.uuid4()
        match = RuleMatchResult(
            rule_id=rule_id,
            rule_name="Test",
            priority=5,
            actions=[],
        )
        assert isinstance(match.rule_id, uuid.UUID)

    def test_rule_match_result_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            RuleMatchResult(  # type: ignore[call-arg]
                rule_id=uuid.uuid4(),
                # rule_name omitted
                priority=1,
                actions=[],
            )


# ---------------------------------------------------------------------------
# RoutingResult
# ---------------------------------------------------------------------------


class TestRoutingResult:
    def _valid_result(self, **overrides: object) -> RoutingResult:
        defaults: dict[str, object] = {
            "email_id": uuid.uuid4(),
            "rules_matched": 2,
            "rules_executed": 2,
            "actions_dispatched": 3,
            "actions_failed": 0,
            "was_routed": True,
            "routing_action_ids": [uuid.uuid4(), uuid.uuid4()],
            "final_state": "routed",
        }
        defaults.update(overrides)
        return RoutingResult(**defaults)  # type: ignore[arg-type]

    def test_routing_result_all_fields_present(self) -> None:
        email_id = uuid.uuid4()
        action_id_1 = uuid.uuid4()
        action_id_2 = uuid.uuid4()
        result = RoutingResult(
            email_id=email_id,
            rules_matched=2,
            rules_executed=2,
            actions_dispatched=3,
            actions_failed=0,
            was_routed=True,
            routing_action_ids=[action_id_1, action_id_2],
            final_state="routed",
        )
        assert result.email_id == email_id
        assert result.rules_matched == 2
        assert result.rules_executed == 2
        assert result.actions_dispatched == 3
        assert result.actions_failed == 0
        assert result.was_routed is True
        assert result.routing_action_ids == [action_id_1, action_id_2]
        assert result.final_state == "routed"

    def test_routing_result_was_routed_true_when_dispatched(self) -> None:
        result = self._valid_result(was_routed=True, final_state="routed")
        assert result.was_routed is True

    def test_routing_result_was_routed_false_when_unrouted(self) -> None:
        result = self._valid_result(
            rules_matched=0,
            rules_executed=0,
            actions_dispatched=0,
            was_routed=False,
            routing_action_ids=[],
            final_state="unrouted",
        )
        assert result.was_routed is False
        assert result.final_state == "unrouted"

    def test_routing_result_empty_action_ids(self) -> None:
        result = self._valid_result(routing_action_ids=[], was_routed=False)
        assert result.routing_action_ids == []

    def test_routing_result_action_ids_are_uuids(self) -> None:
        ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        result = self._valid_result(routing_action_ids=ids)
        for action_id in result.routing_action_ids:
            assert isinstance(action_id, uuid.UUID)

    def test_routing_result_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            RoutingResult(  # type: ignore[call-arg]
                email_id=uuid.uuid4(),
                rules_matched=1,
                rules_executed=1,
                # actions_dispatched omitted
                actions_failed=0,
                was_routed=True,
                routing_action_ids=[],
                final_state="routed",
            )


# ---------------------------------------------------------------------------
# RuleTestResult
# ---------------------------------------------------------------------------


class TestRuleTestResult:
    def _make_context(self) -> RoutingContext:
        return RoutingContext(
            email_id=uuid.uuid4(),
            action_slug="forward",
            type_slug="inquiry",
            confidence="low",
            sender_email="user@corp.com",
            sender_domain="corp.com",
            subject="Product question",
            snippet="Can you tell me more about pricing?",
        )

    def _make_rule_match(self) -> RuleMatchResult:
        return RuleMatchResult(
            rule_id=uuid.uuid4(),
            rule_name="Forward Inquiries",
            priority=2,
            actions=[RoutingActionDef(channel="email", destination="sales@example.com")],
        )

    def test_rule_test_result_dry_run_defaults_to_true(self) -> None:
        ctx = self._make_context()
        result = RuleTestResult(
            context=ctx,
            rules_matched=[],
            would_dispatch=[],
            total_actions=0,
        )
        assert result.dry_run is True

    def test_rule_test_result_dry_run_explicit_true(self) -> None:
        ctx = self._make_context()
        result = RuleTestResult(
            context=ctx,
            rules_matched=[],
            would_dispatch=[],
            total_actions=0,
            dry_run=True,
        )
        assert result.dry_run is True

    def test_rule_test_result_valid_full(self) -> None:
        ctx = self._make_context()
        match = self._make_rule_match()
        action = RoutingActionDef(channel="email", destination="sales@example.com")
        result = RuleTestResult(
            context=ctx,
            rules_matched=[match],
            would_dispatch=[action],
            total_actions=1,
        )
        assert result.context is ctx
        assert len(result.rules_matched) == 1
        assert result.rules_matched[0].rule_name == "Forward Inquiries"
        assert len(result.would_dispatch) == 1
        assert result.would_dispatch[0].channel == "email"
        assert result.total_actions == 1
        assert result.dry_run is True

    def test_rule_test_result_empty_matches(self) -> None:
        ctx = self._make_context()
        result = RuleTestResult(
            context=ctx,
            rules_matched=[],
            would_dispatch=[],
            total_actions=0,
        )
        assert result.rules_matched == []
        assert result.would_dispatch == []
        assert result.total_actions == 0

    def test_rule_test_result_round_trip_serialization(self) -> None:
        ctx = self._make_context()
        match = self._make_rule_match()
        action = RoutingActionDef(
            channel="slack",
            destination="#escalations",
            template_id="tmpl-escalate",
        )
        original = RuleTestResult(
            context=ctx,
            rules_matched=[match],
            would_dispatch=[action],
            total_actions=1,
        )

        serialized = original.model_dump()
        restored = RuleTestResult.model_validate(serialized)

        assert restored.dry_run is True
        assert restored.total_actions == 1
        assert restored.context.email_id == ctx.email_id
        assert restored.context.action_slug == "forward"
        assert restored.context.confidence == "low"
        assert restored.context.sender_name is None
        assert len(restored.rules_matched) == 1
        assert restored.rules_matched[0].rule_name == "Forward Inquiries"
        assert restored.rules_matched[0].actions[0].channel == "email"
        assert len(restored.would_dispatch) == 1
        assert restored.would_dispatch[0].channel == "slack"
        assert restored.would_dispatch[0].template_id == "tmpl-escalate"

    def test_rule_test_result_missing_context_raises(self) -> None:
        with pytest.raises(ValidationError):
            RuleTestResult(  # type: ignore[call-arg]
                rules_matched=[],
                would_dispatch=[],
                total_actions=0,
            )
