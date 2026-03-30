"""Tests for SlackAdapter with mocked AsyncWebClient. No real Slack API calls."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from slack_sdk.errors import SlackApiError

from src.adapters.channel.exceptions import (
    ChannelAuthError,
    ChannelConnectionError,
    ChannelDeliveryError,
    ChannelRateLimitError,
)
from src.adapters.channel.schemas import (
    ChannelCredentials,
    ClassificationInfo,
    ConnectionTestResult,
    Destination,
    RoutingPayload,
    SenderInfo,
)
from src.adapters.channel.slack import SlackAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_slack_api_error(error_code: str, status_code: int = 200) -> SlackApiError:
    """Build a SlackApiError with a given error code and HTTP status."""
    response = MagicMock()
    response.get.return_value = error_code
    response.__getitem__ = lambda self, key: error_code if key == "error" else None
    response.status_code = status_code
    response.headers = {}
    return SlackApiError(message=f"Error: {error_code}", response=response)  # type: ignore[no-untyped-call]


def _make_slack_rate_limit_error(retry_after: str = "30") -> SlackApiError:
    """Build a SlackApiError for HTTP 429 with a Retry-After header."""
    response = MagicMock()
    response.get.return_value = "ratelimited"
    response.__getitem__ = lambda self, key: "ratelimited" if key == "error" else None
    response.status_code = 429
    response.headers = {"Retry-After": retry_after}
    return SlackApiError(message="Rate limited", response=response)  # type: ignore[no-untyped-call]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.channel_slack_timeout_seconds = 10
    settings.channel_snippet_length = 150
    settings.channel_subject_max_length = 100
    settings.channel_destinations_page_size = 200
    return settings


@pytest.fixture
def mock_client() -> AsyncMock:
    """Mock AsyncWebClient with happy-path return values."""
    client = AsyncMock()
    client.auth_test.return_value = {
        "ok": True,
        "team": "Test Workspace",
        "user_id": "U123BOT",
    }
    client.chat_postMessage.return_value = {
        "ok": True,
        "ts": "1234567890.123456",
        "channel": "C123CHANNEL",
    }
    client.conversations_list.return_value = {
        "channels": [
            {"id": "C001", "name": "general"},
            {"id": "C002", "name": "random"},
        ],
        "response_metadata": {"next_cursor": ""},
    }
    return client


@pytest.fixture
def payload() -> RoutingPayload:
    return RoutingPayload(
        email_id="email-001",
        subject="Test Subject",
        sender=SenderInfo(email="alice@example.com", name="Alice"),
        classification=ClassificationInfo(action="reply", type="support", confidence="high"),
        priority="normal",
        snippet="This is the email snippet.",
        dashboard_link="https://dashboard/emails/email-001",
        assigned_to="@jane",
        timestamp=datetime(2025, 1, 20, 10, 0, tzinfo=UTC),
    )


@pytest.fixture
async def connected_adapter(mock_client: AsyncMock, mock_settings: MagicMock) -> SlackAdapter:
    """SlackAdapter that has already completed connect()."""
    adapter = SlackAdapter()
    with (
        patch("src.adapters.channel.slack.AsyncWebClient", return_value=mock_client),
        patch("src.adapters.channel.slack.get_settings", return_value=mock_settings),
    ):
        await adapter.connect(ChannelCredentials(bot_token="xoxb-test-token"))
    return adapter


# ---------------------------------------------------------------------------
# TestConnect
# ---------------------------------------------------------------------------


class TestConnect:
    """Tests for SlackAdapter.connect()."""

    async def test_valid_token_connects(
        self, mock_client: AsyncMock, mock_settings: MagicMock
    ) -> None:
        adapter = SlackAdapter()
        with (
            patch("src.adapters.channel.slack.AsyncWebClient", return_value=mock_client),
            patch("src.adapters.channel.slack.get_settings", return_value=mock_settings),
        ):
            result = await adapter.connect(ChannelCredentials(bot_token="xoxb-test-token"))
        assert result.connected is True

    async def test_returns_workspace_name(
        self, mock_client: AsyncMock, mock_settings: MagicMock
    ) -> None:
        adapter = SlackAdapter()
        with (
            patch("src.adapters.channel.slack.AsyncWebClient", return_value=mock_client),
            patch("src.adapters.channel.slack.get_settings", return_value=mock_settings),
        ):
            result = await adapter.connect(ChannelCredentials(bot_token="xoxb-test-token"))
        assert result.workspace_name == "Test Workspace"

    async def test_returns_bot_user_id(
        self, mock_client: AsyncMock, mock_settings: MagicMock
    ) -> None:
        adapter = SlackAdapter()
        with (
            patch("src.adapters.channel.slack.AsyncWebClient", return_value=mock_client),
            patch("src.adapters.channel.slack.get_settings", return_value=mock_settings),
        ):
            result = await adapter.connect(ChannelCredentials(bot_token="xoxb-test-token"))
        assert result.bot_user_id == "U123BOT"

    async def test_empty_token_raises_value_error(self) -> None:
        adapter = SlackAdapter()
        with pytest.raises(ValueError, match="bot_token must not be empty"):
            await adapter.connect(ChannelCredentials(bot_token=""))

    async def test_token_without_xoxb_prefix_raises_value_error(self) -> None:
        adapter = SlackAdapter()
        with pytest.raises(ValueError, match="xoxb-"):
            await adapter.connect(ChannelCredentials(bot_token="xoxa-wrong-prefix"))

    async def test_slack_auth_error_raises_channel_auth_error(
        self, mock_client: AsyncMock, mock_settings: MagicMock
    ) -> None:
        mock_client.auth_test.side_effect = _make_slack_api_error("invalid_auth")
        adapter = SlackAdapter()
        with (
            patch("src.adapters.channel.slack.AsyncWebClient", return_value=mock_client),
            patch("src.adapters.channel.slack.get_settings", return_value=mock_settings),
            pytest.raises(ChannelAuthError),
        ):
            await adapter.connect(ChannelCredentials(bot_token="xoxb-test-token"))

    async def test_timeout_raises_channel_connection_error(
        self, mock_client: AsyncMock, mock_settings: MagicMock
    ) -> None:
        mock_client.auth_test.side_effect = TimeoutError()
        adapter = SlackAdapter()
        with (
            patch("src.adapters.channel.slack.AsyncWebClient", return_value=mock_client),
            patch("src.adapters.channel.slack.get_settings", return_value=mock_settings),
            pytest.raises(ChannelConnectionError),
        ):
            await adapter.connect(ChannelCredentials(bot_token="xoxb-test-token"))

    async def test_network_error_raises_channel_connection_error(
        self, mock_client: AsyncMock, mock_settings: MagicMock
    ) -> None:
        mock_client.auth_test.side_effect = aiohttp.ClientConnectionError("DNS failure")
        adapter = SlackAdapter()
        with (
            patch("src.adapters.channel.slack.AsyncWebClient", return_value=mock_client),
            patch("src.adapters.channel.slack.get_settings", return_value=mock_settings),
            pytest.raises(ChannelConnectionError),
        ):
            await adapter.connect(ChannelCredentials(bot_token="xoxb-test-token"))


# ---------------------------------------------------------------------------
# TestSendNotification
# ---------------------------------------------------------------------------


class TestSendNotification:
    """Tests for SlackAdapter.send_notification()."""

    async def test_successful_delivery(
        self,
        connected_adapter: SlackAdapter,
        payload: RoutingPayload,
        mock_settings: MagicMock,
    ) -> None:
        with patch("src.adapters.channel.formatters.get_settings", return_value=mock_settings):
            result = await connected_adapter.send_notification(payload, "C123CHANNEL")
        assert result.success is True
        assert result.message_ts == "1234567890.123456"
        assert result.channel_id == "C123CHANNEL"

    async def test_empty_destination_raises_value_error(
        self,
        connected_adapter: SlackAdapter,
        payload: RoutingPayload,
        mock_settings: MagicMock,
    ) -> None:
        with (
            patch("src.adapters.channel.formatters.get_settings", return_value=mock_settings),
            pytest.raises(ValueError, match="destination_id must not be empty"),
        ):
            await connected_adapter.send_notification(payload, "")

    async def test_not_connected_raises_channel_auth_error(
        self, payload: RoutingPayload, mock_settings: MagicMock
    ) -> None:
        fresh_adapter = SlackAdapter()
        with (
            patch("src.adapters.channel.formatters.get_settings", return_value=mock_settings),
            pytest.raises(ChannelAuthError),
        ):
            await fresh_adapter.send_notification(payload, "C123CHANNEL")

    async def test_auth_error_raises_channel_auth_error(
        self,
        connected_adapter: SlackAdapter,
        payload: RoutingPayload,
        mock_settings: MagicMock,
    ) -> None:
        connected_adapter._client.chat_postMessage.side_effect = _make_slack_api_error(  # type: ignore[union-attr]
            "invalid_auth"
        )
        with (
            patch("src.adapters.channel.formatters.get_settings", return_value=mock_settings),
            pytest.raises(ChannelAuthError),
        ):
            await connected_adapter.send_notification(payload, "C123CHANNEL")

    async def test_token_revoked_raises_channel_auth_error(
        self,
        connected_adapter: SlackAdapter,
        payload: RoutingPayload,
        mock_settings: MagicMock,
    ) -> None:
        connected_adapter._client.chat_postMessage.side_effect = _make_slack_api_error(  # type: ignore[union-attr]
            "token_revoked"
        )
        with (
            patch("src.adapters.channel.formatters.get_settings", return_value=mock_settings),
            pytest.raises(ChannelAuthError),
        ):
            await connected_adapter.send_notification(payload, "C123CHANNEL")

    async def test_channel_not_found_raises_delivery_error(
        self,
        connected_adapter: SlackAdapter,
        payload: RoutingPayload,
        mock_settings: MagicMock,
    ) -> None:
        connected_adapter._client.chat_postMessage.side_effect = _make_slack_api_error(  # type: ignore[union-attr]
            "channel_not_found"
        )
        with (
            patch("src.adapters.channel.formatters.get_settings", return_value=mock_settings),
            pytest.raises(ChannelDeliveryError),
        ):
            await connected_adapter.send_notification(payload, "C_MISSING")

    async def test_is_archived_raises_delivery_error(
        self,
        connected_adapter: SlackAdapter,
        payload: RoutingPayload,
        mock_settings: MagicMock,
    ) -> None:
        connected_adapter._client.chat_postMessage.side_effect = _make_slack_api_error(  # type: ignore[union-attr]
            "is_archived"
        )
        with (
            patch("src.adapters.channel.formatters.get_settings", return_value=mock_settings),
            pytest.raises(ChannelDeliveryError),
        ):
            await connected_adapter.send_notification(payload, "C_ARCHIVED")

    async def test_rate_limit_raises_rate_limit_error(
        self,
        connected_adapter: SlackAdapter,
        payload: RoutingPayload,
        mock_settings: MagicMock,
    ) -> None:
        connected_adapter._client.chat_postMessage.side_effect = _make_slack_rate_limit_error(  # type: ignore[union-attr]
            retry_after="30"
        )
        raised: ChannelRateLimitError | None = None
        try:
            with patch("src.adapters.channel.formatters.get_settings", return_value=mock_settings):
                await connected_adapter.send_notification(payload, "C123CHANNEL")
        except ChannelRateLimitError as exc:
            raised = exc
        assert raised is not None
        assert raised.retry_after_seconds == 30

    async def test_timeout_raises_connection_error(
        self,
        connected_adapter: SlackAdapter,
        payload: RoutingPayload,
        mock_settings: MagicMock,
    ) -> None:
        connected_adapter._client.chat_postMessage.side_effect = TimeoutError()  # type: ignore[union-attr]
        with (
            patch("src.adapters.channel.formatters.get_settings", return_value=mock_settings),
            pytest.raises(ChannelConnectionError),
        ):
            await connected_adapter.send_notification(payload, "C123CHANNEL")

    async def test_passes_blocks_to_slack(
        self,
        connected_adapter: SlackAdapter,
        payload: RoutingPayload,
        mock_settings: MagicMock,
    ) -> None:
        with patch("src.adapters.channel.formatters.get_settings", return_value=mock_settings):
            await connected_adapter.send_notification(payload, "C123CHANNEL")

        call_kwargs = connected_adapter._client.chat_postMessage.call_args.kwargs  # type: ignore[union-attr]
        assert "blocks" in call_kwargs
        assert isinstance(call_kwargs["blocks"], list)
        assert len(call_kwargs["blocks"]) > 0


# ---------------------------------------------------------------------------
# TestTestConnection
# ---------------------------------------------------------------------------


class TestTestConnection:
    """Tests for SlackAdapter.test_connection()."""

    async def test_success(self, connected_adapter: SlackAdapter) -> None:
        result = await connected_adapter.test_connection()
        assert result.success is True

    async def test_not_connected_returns_failure(self) -> None:
        fresh_adapter = SlackAdapter()
        result = await fresh_adapter.test_connection()
        assert result.success is False

    async def test_never_raises_on_error(self, connected_adapter: SlackAdapter) -> None:
        connected_adapter._client.auth_test.side_effect = RuntimeError("unexpected crash")  # type: ignore[union-attr]
        # Must not raise — health-check silences ALL errors (noqa: BLE001)
        result = await connected_adapter.test_connection()
        assert isinstance(result, ConnectionTestResult)
        assert result.success is False

    async def test_measures_latency(self, connected_adapter: SlackAdapter) -> None:
        result = await connected_adapter.test_connection()
        assert result.latency_ms >= 0

    async def test_returns_workspace_name(self, connected_adapter: SlackAdapter) -> None:
        result = await connected_adapter.test_connection()
        assert result.workspace_name == "Test Workspace"


# ---------------------------------------------------------------------------
# TestGetAvailableDestinations
# ---------------------------------------------------------------------------


class TestGetAvailableDestinations:
    """Tests for SlackAdapter.get_available_destinations()."""

    async def test_returns_destinations(
        self, connected_adapter: SlackAdapter, mock_settings: MagicMock
    ) -> None:
        with patch("src.adapters.channel.slack.get_settings", return_value=mock_settings):
            result = await connected_adapter.get_available_destinations()
        assert len(result) == 2
        assert all(isinstance(d, Destination) for d in result)

    async def test_destination_names_have_hash_prefix(
        self, connected_adapter: SlackAdapter, mock_settings: MagicMock
    ) -> None:
        with patch("src.adapters.channel.slack.get_settings", return_value=mock_settings):
            result = await connected_adapter.get_available_destinations()
        assert all(d.name.startswith("#") for d in result)

    async def test_pagination_two_pages(
        self, connected_adapter: SlackAdapter, mock_settings: MagicMock
    ) -> None:
        page1 = {
            "channels": [{"id": "C001", "name": "general"}],
            "response_metadata": {"next_cursor": "abc123"},
        }
        page2 = {
            "channels": [{"id": "C002", "name": "random"}],
            "response_metadata": {"next_cursor": ""},
        }
        connected_adapter._client.conversations_list.side_effect = [page1, page2]  # type: ignore[union-attr]
        with patch("src.adapters.channel.slack.get_settings", return_value=mock_settings):
            result = await connected_adapter.get_available_destinations()
        assert len(result) == 2
        ids = [d.id for d in result]
        assert "C001" in ids
        assert "C002" in ids

    async def test_empty_channels(
        self, connected_adapter: SlackAdapter, mock_settings: MagicMock
    ) -> None:
        connected_adapter._client.conversations_list.return_value = {  # type: ignore[union-attr]
            "channels": [],
            "response_metadata": {"next_cursor": ""},
        }
        with patch("src.adapters.channel.slack.get_settings", return_value=mock_settings):
            result = await connected_adapter.get_available_destinations()
        assert result == []

    async def test_not_connected_raises(self, mock_settings: MagicMock) -> None:
        fresh_adapter = SlackAdapter()
        with (
            patch("src.adapters.channel.slack.get_settings", return_value=mock_settings),
            pytest.raises(ChannelAuthError),
        ):
            await fresh_adapter.get_available_destinations()

    async def test_auth_error_propagates(
        self, connected_adapter: SlackAdapter, mock_settings: MagicMock
    ) -> None:
        connected_adapter._client.conversations_list.side_effect = _make_slack_api_error(  # type: ignore[union-attr]
            "invalid_auth"
        )
        with (
            patch("src.adapters.channel.slack.get_settings", return_value=mock_settings),
            pytest.raises(ChannelAuthError),
        ):
            await connected_adapter.get_available_destinations()
