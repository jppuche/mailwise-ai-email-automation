"""SlackAdapter — concrete ChannelAdapter using slack-sdk AsyncWebClient.

contract-docstrings:
  Invariants: ``ChannelCredentials`` must be provided via ``connect()``
    before any operation except ``test_connection()``.
  Guarantees: Raw slack-sdk response dicts never escape this module. All
    returns are typed adapter schemas.
  Errors raised: Typed ``ChannelAdapterError`` subclasses.
  Errors silenced: ``test_connection()`` silences all errors.
  External state: Slack API via slack-sdk AsyncWebClient.

try-except D7: Every AsyncWebClient call uses structured try/except for
  ``SlackApiError``, ``asyncio.TimeoutError``, and connection errors.
try-except D8: Argument validation uses conditionals, not try/except.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

import aiohttp
import structlog
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from src.adapters.channel.base import ChannelAdapter
from src.adapters.channel.exceptions import (
    ChannelAdapterError,
    ChannelAuthError,
    ChannelConnectionError,
    ChannelDeliveryError,
    ChannelRateLimitError,
)
from src.adapters.channel.formatters import SlackBlockKitFormatter
from src.adapters.channel.schemas import (
    ChannelCredentials,
    ConnectionStatus,
    ConnectionTestResult,
    DeliveryResult,
    Destination,
    RoutingPayload,
)
from src.core.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Slack error code classification (Cat 3: no magic strings)
# ---------------------------------------------------------------------------

_AUTH_ERROR_CODES: frozenset[str] = frozenset({"invalid_auth", "token_revoked", "missing_scope"})

_DELIVERY_ERROR_CODES: frozenset[str] = frozenset(
    {"channel_not_found", "is_archived", "not_in_channel", "cant_invite_self"}
)


class SlackAdapter(ChannelAdapter):
    """Slack notification adapter using slack-sdk AsyncWebClient."""

    def __init__(self) -> None:
        self._client: AsyncWebClient | None = None
        self._connected: bool = False
        self._formatter = SlackBlockKitFormatter()

    # -- Private helpers ---------------------------------------------------

    def _ensure_connected(self) -> None:
        """Verify adapter is connected; raise ChannelAuthError if not."""
        if not self._connected or self._client is None:
            raise ChannelAuthError("Adapter not connected — call connect() first")

    def _map_slack_error(self, exc: SlackApiError) -> ChannelAdapterError:
        """Map a SlackApiError to the appropriate domain exception.

        HTTP 429 check comes first — Slack returns 429 status even though
        most errors return 200 OK.
        """
        # Rate limit (429) — check status_code first
        if exc.response.status_code == 429:
            retry_after: int | None = None
            # D8 exception: int() has no conditional alternative for str→int
            with contextlib.suppress(ValueError, TypeError):
                retry_after = int(exc.response.headers.get("Retry-After", 0))
            return ChannelRateLimitError(
                "Slack rate limit exceeded",
                retry_after_seconds=retry_after,
                original_error=exc,
            )

        # Classify by error code string
        error_code: str = exc.response.get("error", "unknown")

        if error_code in _AUTH_ERROR_CODES:
            return ChannelAuthError(
                f"Slack auth error: {error_code}",
                original_error=exc,
            )
        if error_code in _DELIVERY_ERROR_CODES:
            return ChannelDeliveryError(
                f"Slack delivery error: {error_code}",
                original_error=exc,
            )
        return ChannelDeliveryError(
            f"Slack API error: {error_code}",
            original_error=exc,
        )

    # -- Public interface (ChannelAdapter ABC) -----------------------------

    async def connect(self, credentials: ChannelCredentials) -> ConnectionStatus:
        # D8: precondition validation via conditionals
        if not credentials.bot_token:
            raise ValueError("credentials.bot_token must not be empty")
        if not credentials.bot_token.startswith("xoxb-"):
            raise ValueError("credentials.bot_token must have 'xoxb-' prefix")

        settings = get_settings()
        client = AsyncWebClient(
            token=credentials.bot_token,
            timeout=settings.channel_slack_timeout_seconds,
        )

        # D7: external-state operation
        try:
            response = await client.auth_test()
        except SlackApiError as exc:
            raise self._map_slack_error(exc) from exc
        except TimeoutError as exc:
            raise ChannelConnectionError(
                "Slack API timeout during connect", original_error=exc
            ) from exc
        except aiohttp.ClientConnectionError as exc:
            raise ChannelConnectionError(
                f"Network error during connect: {exc}", original_error=exc
            ) from exc

        self._client = client
        self._connected = True

        logger.info(
            "slack_connected",
            workspace=response.get("team"),
            bot_user_id=response.get("user_id"),
        )

        return ConnectionStatus(
            connected=True,
            workspace_name=response.get("team"),
            bot_user_id=response.get("user_id"),
        )

    async def send_notification(
        self,
        payload: RoutingPayload,
        destination_id: str,
    ) -> DeliveryResult:
        # D8: precondition validation via conditionals
        if not destination_id:
            raise ValueError("destination_id must not be empty")
        self._ensure_connected()
        assert self._client is not None  # narrowed by _ensure_connected

        # Local computation — no try/except
        blocks = self._formatter.build_blocks(payload)
        fallback_text = f"[{payload.priority.upper()}] {payload.subject}"

        # D7: external-state operation
        try:
            response = await self._client.chat_postMessage(
                channel=destination_id,
                blocks=blocks,
                text=fallback_text,
            )
        except SlackApiError as exc:
            raise self._map_slack_error(exc) from exc
        except TimeoutError as exc:
            raise ChannelConnectionError("Slack API timeout", original_error=exc) from exc
        except aiohttp.ClientConnectionError as exc:
            raise ChannelConnectionError(f"Network error: {exc}", original_error=exc) from exc

        logger.info(
            "slack_notification_sent",
            email_id=payload.email_id,
            channel=destination_id,
            message_ts=response.get("ts"),
        )

        return DeliveryResult(
            success=True,
            message_ts=response.get("ts"),
            channel_id=response.get("channel"),
        )

    async def test_connection(self) -> ConnectionTestResult:
        if self._client is None or not self._connected:
            return ConnectionTestResult(
                success=False,
                latency_ms=0,
                error_detail="Adapter not connected — credentials not loaded",
            )

        start = time.monotonic()
        try:
            response = await self._client.auth_test()
            latency_ms = int((time.monotonic() - start) * 1000)
            return ConnectionTestResult(
                success=True,
                workspace_name=response.get("team"),
                latency_ms=latency_ms,
            )
        except Exception as exc:  # noqa: BLE001 — health-check silences ALL errors
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.warning("slack_test_connection_failed", error=str(exc))
            return ConnectionTestResult(
                success=False,
                latency_ms=latency_ms,
                error_detail=str(exc),
            )

    async def get_available_destinations(self) -> list[Destination]:
        self._ensure_connected()
        assert self._client is not None  # narrowed by _ensure_connected

        settings = get_settings()
        destinations: list[Destination] = []
        cursor: str | None = None

        # D7: external-state operation with pagination
        try:
            while True:
                kwargs: dict[str, object] = {
                    "limit": settings.channel_destinations_page_size,
                    "exclude_archived": True,
                }
                if cursor:
                    kwargs["cursor"] = cursor

                response = await self._client.conversations_list(**kwargs)  # type: ignore[arg-type]

                channels: list[Any] = response.get("channels", [])
                for channel in channels:
                    destinations.append(
                        Destination(
                            id=channel["id"],
                            name=f"#{channel.get('name', '')}",
                            type="channel",
                        )
                    )

                metadata: dict[str, Any] = response.get("response_metadata", {})
                next_cursor = metadata.get("next_cursor") or ""
                if not next_cursor:
                    break
                cursor = next_cursor

        except SlackApiError as exc:
            raise self._map_slack_error(exc) from exc
        except TimeoutError as exc:
            raise ChannelConnectionError("Slack API timeout", original_error=exc) from exc
        except aiohttp.ClientConnectionError as exc:
            raise ChannelConnectionError(f"Network error: {exc}", original_error=exc) from exc

        logger.info(
            "slack_destinations_listed",
            count=len(destinations),
        )

        return destinations
