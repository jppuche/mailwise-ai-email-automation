"""Unit tests for channel adapter boundary schemas.

Validates Pydantic models for SenderInfo, ClassificationInfo, RoutingPayload,
Destination, ChannelCredentials, ConnectionStatus, ConnectionTestResult, and
DeliveryResult.
No external dependencies — pure schema validation.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.adapters.channel.schemas import (
    ChannelCredentials,
    ClassificationInfo,
    ConnectionStatus,
    ConnectionTestResult,
    DeliveryResult,
    Destination,
    RoutingPayload,
    SenderInfo,
)

# ---------------------------------------------------------------------------
# SenderInfo
# ---------------------------------------------------------------------------


class TestSenderInfo:
    """Validates SenderInfo construction and optional name field."""

    def test_valid_with_name(self) -> None:
        sender = SenderInfo(email="alice@example.com", name="Alice")
        assert sender.email == "alice@example.com"
        assert sender.name == "Alice"

    def test_valid_without_name(self) -> None:
        sender = SenderInfo(email="alice@example.com")
        assert sender.name is None

    def test_name_none_explicit(self) -> None:
        sender = SenderInfo(email="alice@example.com", name=None)
        assert sender.name is None

    def test_missing_email_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SenderInfo()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ClassificationInfo
# ---------------------------------------------------------------------------


class TestClassificationInfo:
    """Validates ClassificationInfo Literal constraint on confidence."""

    def test_valid_high_confidence(self) -> None:
        info = ClassificationInfo(action="reply", type="support", confidence="high")
        assert info.action == "reply"
        assert info.type == "support"
        assert info.confidence == "high"

    def test_valid_low_confidence(self) -> None:
        info = ClassificationInfo(action="inform", type="notification", confidence="low")
        assert info.confidence == "low"

    def test_invalid_confidence_medium_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClassificationInfo(
                action="reply",
                type="support",
                confidence="medium",  # runtime Literal mismatch validated by Pydantic, not mypy
            )

    def test_invalid_confidence_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClassificationInfo(
                action="reply",
                type="support",
                confidence="",  # runtime Literal mismatch validated by Pydantic, not mypy
            )

    def test_missing_action_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClassificationInfo(type="support", confidence="high")  # type: ignore[call-arg]

    def test_missing_confidence_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClassificationInfo(action="reply", type="support")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# RoutingPayload
# ---------------------------------------------------------------------------


class TestRoutingPayload:
    """Validates RoutingPayload nested model construction and constraints."""

    def _make_payload(self, **overrides: object) -> RoutingPayload:
        defaults: dict[str, object] = {
            "email_id": "email-001",
            "subject": "Support request",
            "sender": SenderInfo(email="customer@example.com", name="Customer"),
            "classification": ClassificationInfo(action="reply", type="support", confidence="high"),
            "priority": "normal",
            "snippet": "I need help with my account...",
            "dashboard_link": "https://app.mailwise.io/emails/email-001",
            "timestamp": datetime(2026, 2, 21, 12, 0, tzinfo=UTC),
        }
        defaults.update(overrides)
        return RoutingPayload(**defaults)  # type: ignore[arg-type]

    def test_valid_full_construction(self) -> None:
        payload = self._make_payload(assigned_to="agent@example.com")
        assert payload.email_id == "email-001"
        assert payload.subject == "Support request"
        assert payload.sender.email == "customer@example.com"
        assert payload.classification.confidence == "high"
        assert payload.priority == "normal"
        assert payload.assigned_to == "agent@example.com"

    def test_assigned_to_defaults_to_none(self) -> None:
        payload = self._make_payload()
        assert payload.assigned_to is None

    def test_valid_priority_urgent(self) -> None:
        payload = self._make_payload(priority="urgent")
        assert payload.priority == "urgent"

    def test_valid_priority_low(self) -> None:
        payload = self._make_payload(priority="low")
        assert payload.priority == "low"

    def test_invalid_priority_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make_payload(priority="critical")

    def test_timestamp_accepts_aware_datetime(self) -> None:
        ts = datetime(2026, 2, 21, 9, 30, tzinfo=UTC)
        payload = self._make_payload(timestamp=ts)
        assert payload.timestamp == ts

    def test_nested_sender_validation(self) -> None:
        """Nested SenderInfo is validated as a full model."""
        payload = self._make_payload(sender=SenderInfo(email="noreply@corp.com"))
        assert payload.sender.email == "noreply@corp.com"
        assert payload.sender.name is None

    def test_missing_email_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RoutingPayload(
                subject="Hello",
                sender=SenderInfo(email="a@b.com"),
                classification=ClassificationInfo(
                    action="reply", type="support", confidence="high"
                ),
                priority="normal",
                snippet="...",
                dashboard_link="https://example.com",
                timestamp=datetime.now(tz=UTC),
            )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Destination
# ---------------------------------------------------------------------------


class TestDestination:
    """Validates Destination construction and type Literal constraint."""

    def test_valid_channel_type(self) -> None:
        dest = Destination(id="C012AB3CD", name="#general", type="channel")
        assert dest.id == "C012AB3CD"
        assert dest.name == "#general"
        assert dest.type == "channel"

    def test_valid_dm_type(self) -> None:
        dest = Destination(id="U09876543", name="@alice", type="dm")
        assert dest.type == "dm"

    def test_valid_group_type(self) -> None:
        dest = Destination(id="G0123WXYZ", name="eng-alerts", type="group")
        assert dest.type == "group"

    def test_invalid_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Destination(
                id="X123",
                name="unknown",
                type="webhook",
            )

    def test_missing_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Destination(name="#general", type="channel")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ChannelCredentials
# ---------------------------------------------------------------------------


class TestChannelCredentials:
    """Validates ChannelCredentials construction."""

    def test_valid_construction(self) -> None:
        creds = ChannelCredentials(bot_token="xoxb-123-abc")
        assert creds.bot_token == "xoxb-123-abc"

    def test_missing_bot_token_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ChannelCredentials()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ConnectionStatus
# ---------------------------------------------------------------------------


class TestConnectionStatus:
    """Validates ConnectionStatus optional fields default to None."""

    def test_connected_with_all_fields(self) -> None:
        status = ConnectionStatus(
            connected=True,
            workspace_name="MailwiseHQ",
            bot_user_id="U0BOT123",
            error=None,
        )
        assert status.connected is True
        assert status.workspace_name == "MailwiseHQ"
        assert status.bot_user_id == "U0BOT123"
        assert status.error is None

    def test_disconnected_with_error(self) -> None:
        status = ConnectionStatus(connected=False, error="invalid_auth")
        assert status.connected is False
        assert status.error == "invalid_auth"
        assert status.workspace_name is None
        assert status.bot_user_id is None

    def test_all_optional_fields_default_to_none(self) -> None:
        status = ConnectionStatus(connected=True)
        assert status.workspace_name is None
        assert status.bot_user_id is None
        assert status.error is None


# ---------------------------------------------------------------------------
# ConnectionTestResult
# ---------------------------------------------------------------------------


class TestConnectionTestResult:
    """Validates ConnectionTestResult; latency_ms is required."""

    def test_success_result(self) -> None:
        result = ConnectionTestResult(
            success=True,
            workspace_name="MailwiseHQ",
            latency_ms=42,
        )
        assert result.success is True
        assert result.workspace_name == "MailwiseHQ"
        assert result.latency_ms == 42
        assert result.error_detail is None

    def test_failure_result_with_error_detail(self) -> None:
        result = ConnectionTestResult(
            success=False,
            latency_ms=0,
            error_detail="not_authed",
        )
        assert result.success is False
        assert result.error_detail == "not_authed"
        assert result.workspace_name is None

    def test_latency_ms_required(self) -> None:
        """latency_ms has no default — must be supplied."""
        with pytest.raises(ValidationError):
            ConnectionTestResult(success=True)  # type: ignore[call-arg]

    def test_optional_fields_default_to_none(self) -> None:
        result = ConnectionTestResult(success=True, latency_ms=10)
        assert result.workspace_name is None
        assert result.error_detail is None


# ---------------------------------------------------------------------------
# DeliveryResult
# ---------------------------------------------------------------------------


class TestDeliveryResult:
    """Validates DeliveryResult; all optional fields default to None."""

    def test_success_result(self) -> None:
        result = DeliveryResult(
            success=True,
            message_ts="1740134400.000100",
            channel_id="C012AB3CD",
        )
        assert result.success is True
        assert result.message_ts == "1740134400.000100"
        assert result.channel_id == "C012AB3CD"
        assert result.error_detail is None

    def test_failure_result_with_error_detail(self) -> None:
        result = DeliveryResult(success=False, error_detail="channel_not_found")
        assert result.success is False
        assert result.error_detail == "channel_not_found"
        assert result.message_ts is None
        assert result.channel_id is None

    def test_all_optional_fields_default_to_none(self) -> None:
        result = DeliveryResult(success=True)
        assert result.message_ts is None
        assert result.channel_id is None
        assert result.error_detail is None

    def test_missing_success_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DeliveryResult()  # type: ignore[call-arg]
