"""Contract tests for the ChannelAdapter ABC.

Uses a ``MockChannelAdapter`` that implements all 4 abstract methods.
Verifies that *any* correct implementation satisfies the contract:
correct return types, expected exceptions for invalid inputs,
``test_connection()`` never raises, ABC enforcement.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.adapters.channel.base import ChannelAdapter
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
# MockChannelAdapter — minimal concrete implementation
# ---------------------------------------------------------------------------


class MockChannelAdapter(ChannelAdapter):
    """Simplest valid implementation satisfying the ABC contract."""

    def __init__(self) -> None:
        self._connected = False

    async def connect(self, credentials: ChannelCredentials) -> ConnectionStatus:
        if not credentials.bot_token:
            raise ValueError("bot_token must not be empty")
        if not credentials.bot_token.startswith("xoxb-"):
            raise ValueError("bot_token must have 'xoxb-' prefix")
        self._connected = True
        return ConnectionStatus(
            connected=True,
            workspace_name="MockWorkspace",
            bot_user_id="U000",
        )

    async def send_notification(
        self,
        payload: RoutingPayload,
        destination_id: str,
    ) -> DeliveryResult:
        if not destination_id:
            raise ValueError("destination_id must not be empty")
        return DeliveryResult(
            success=True,
            message_ts="mock.ts",
            channel_id=destination_id,
        )

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(success=True, latency_ms=1)

    async def get_available_destinations(self) -> list[Destination]:
        return [Destination(id="C123", name="#general", type="channel")]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def adapter() -> MockChannelAdapter:
    return MockChannelAdapter()


@pytest.fixture
def credentials() -> ChannelCredentials:
    return ChannelCredentials(bot_token="xoxb-test-token")


@pytest.fixture
def payload() -> RoutingPayload:
    return RoutingPayload(
        email_id="email-001",
        subject="Test Subject",
        sender=SenderInfo(email="alice@example.com", name="Alice"),
        classification=ClassificationInfo(
            action="reply",
            type="support",
            confidence="high",
        ),
        priority="normal",
        snippet="This is the email snippet.",
        dashboard_link="https://dashboard/emails/email-001",
        assigned_to="@jane",
        timestamp=datetime(2025, 1, 20, 10, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# ABC satisfiability
# ---------------------------------------------------------------------------


class TestABCSatisfiability:
    """MockChannelAdapter must be instantiable and recognised as ChannelAdapter."""

    def test_can_instantiate_mock(self) -> None:
        adapter = MockChannelAdapter()
        assert adapter is not None

    def test_is_instance_of_channel_adapter(self) -> None:
        adapter = MockChannelAdapter()
        assert isinstance(adapter, ChannelAdapter)


# ---------------------------------------------------------------------------
# connect() contract
# ---------------------------------------------------------------------------


class TestConnectContract:
    """Any ChannelAdapter.connect() implementation must satisfy these."""

    async def test_returns_connection_status(
        self,
        adapter: MockChannelAdapter,
        credentials: ChannelCredentials,
    ) -> None:
        result = await adapter.connect(credentials)
        assert isinstance(result, ConnectionStatus)

    async def test_connected_is_true(
        self,
        adapter: MockChannelAdapter,
        credentials: ChannelCredentials,
    ) -> None:
        result = await adapter.connect(credentials)
        assert result.connected is True

    async def test_empty_token_raises_value_error(
        self,
        adapter: MockChannelAdapter,
    ) -> None:
        with pytest.raises(ValueError, match="bot_token"):
            await adapter.connect(ChannelCredentials(bot_token=""))

    async def test_invalid_prefix_raises_value_error(
        self,
        adapter: MockChannelAdapter,
    ) -> None:
        with pytest.raises(ValueError, match="xoxb-"):
            await adapter.connect(ChannelCredentials(bot_token="invalid-token"))


# ---------------------------------------------------------------------------
# send_notification() contract
# ---------------------------------------------------------------------------


class TestSendNotificationContract:
    """Any ChannelAdapter.send_notification() implementation must satisfy these."""

    async def test_returns_delivery_result(
        self,
        adapter: MockChannelAdapter,
        payload: RoutingPayload,
    ) -> None:
        result = await adapter.send_notification(payload, "C123CHANNEL")
        assert isinstance(result, DeliveryResult)

    async def test_success_is_true(
        self,
        adapter: MockChannelAdapter,
        payload: RoutingPayload,
    ) -> None:
        result = await adapter.send_notification(payload, "C123CHANNEL")
        assert result.success is True

    async def test_empty_destination_raises_value_error(
        self,
        adapter: MockChannelAdapter,
        payload: RoutingPayload,
    ) -> None:
        with pytest.raises(ValueError, match="destination_id"):
            await adapter.send_notification(payload, "")


# ---------------------------------------------------------------------------
# test_connection() contract
# ---------------------------------------------------------------------------


class TestTestConnectionContract:
    """test_connection() must NEVER raise — always returns ConnectionTestResult."""

    async def test_returns_connection_test_result(
        self,
        adapter: MockChannelAdapter,
    ) -> None:
        result = await adapter.test_connection()
        assert isinstance(result, ConnectionTestResult)

    async def test_never_raises(
        self,
        adapter: MockChannelAdapter,
    ) -> None:
        # Must complete without exception on a fresh (unconnected) adapter.
        result = await adapter.test_connection()
        assert result is not None

    async def test_has_latency_ms(
        self,
        adapter: MockChannelAdapter,
    ) -> None:
        result = await adapter.test_connection()
        assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# get_available_destinations() contract
# ---------------------------------------------------------------------------


class TestGetAvailableDestinationsContract:
    """Any ChannelAdapter.get_available_destinations() implementation must satisfy these."""

    async def test_returns_list_of_destinations(
        self,
        adapter: MockChannelAdapter,
    ) -> None:
        result = await adapter.get_available_destinations()
        assert isinstance(result, list)
        assert all(isinstance(d, Destination) for d in result)

    async def test_destinations_have_required_fields(
        self,
        adapter: MockChannelAdapter,
    ) -> None:
        result = await adapter.get_available_destinations()
        assert len(result) >= 1
        for destination in result:
            assert isinstance(destination.id, str)
            assert isinstance(destination.name, str)
            assert isinstance(destination.type, str)


# ---------------------------------------------------------------------------
# ABC enforcement
# ---------------------------------------------------------------------------


class TestABCEnforcement:
    """Cannot instantiate ChannelAdapter without implementing all methods."""

    def test_cannot_instantiate_abc_directly(self) -> None:
        with pytest.raises(TypeError, match="abstract method"):
            ChannelAdapter()  # type: ignore[abstract]

    def test_partial_implementation_raises(self) -> None:
        class PartialAdapter(ChannelAdapter):
            async def connect(
                self,
                credentials: ChannelCredentials,
            ) -> ConnectionStatus:
                return ConnectionStatus(connected=True)

        with pytest.raises(TypeError, match="abstract method"):
            PartialAdapter()  # type: ignore[abstract]
