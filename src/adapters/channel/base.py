"""ChannelAdapter ABC — provider-agnostic notification channel interface.

contract-docstrings:
  Invariants: Adapter must be connected (via ``connect()``) before any
    operation except ``test_connection()``.
  Guarantees: All returned values are fully typed (no raw dicts cross the
    boundary). Destination enumeration silently excludes inaccessible channels.
  Errors raised: Typed exceptions from ``adapters.channel.exceptions``.
  Errors silenced: Only ``test_connection()`` silences errors.
  External state: Channel provider API (Slack, etc.).

try-except D7: External-state operations use structured try/except with
  specific exception types mapped to domain exceptions.
"""

from __future__ import annotations

import abc

from src.adapters.channel.schemas import (
    ChannelCredentials,
    ConnectionStatus,
    ConnectionTestResult,
    DeliveryResult,
    Destination,
    RoutingPayload,
)


class ChannelAdapter(abc.ABC):
    """Abstract base for notification channel adapters.

    Implementations must handle API authentication, message formatting,
    and structured error mapping. The adapter boundary is the typed schemas
    in ``adapters.channel.schemas`` — raw provider dicts never leak past
    this layer.
    """

    @abc.abstractmethod
    async def connect(self, credentials: ChannelCredentials) -> ConnectionStatus:
        """Establish a connection to the channel provider.

        Preconditions:
          - ``credentials.bot_token`` is non-empty with "xoxb-" prefix.

        Guarantees:
          - On success, adapter is ready for subsequent operations.
          - Returns ``ConnectionStatus`` with ``connected=True``.

        Errors raised:
          - ``ValueError`` if ``bot_token`` is empty or lacks "xoxb-" prefix.
          - ``ChannelAuthError`` if the provider rejects the token.
          - ``ChannelConnectionError`` on network / timeout failure.

        Errors silenced: None.
        """

    @abc.abstractmethod
    async def send_notification(
        self,
        payload: RoutingPayload,
        destination_id: str,
    ) -> DeliveryResult:
        """Send a routing notification to the specified destination.

        Preconditions:
          - ``destination_id`` is a non-empty channel or user ID.
          - ``payload.email_id`` is non-empty.
          - Adapter is connected.

        Guarantees:
          - On success, returns ``DeliveryResult(success=True)``.
          - ``message_ts`` is the Slack message timestamp for thread replies.

        Errors raised:
          - ``ValueError`` if ``destination_id`` is empty.
          - ``ChannelAuthError`` if adapter is not connected, or on auth errors.
          - ``ChannelRateLimitError`` on HTTP 429 (after SDK exhausts retries).
          - ``ChannelConnectionError`` on network / timeout failure.
          - ``ChannelDeliveryError`` on delivery-specific failures.

        Errors silenced: None.
        """

    @abc.abstractmethod
    async def test_connection(self) -> ConnectionTestResult:
        """Non-destructive connectivity check (health-check semantics).

        This method NEVER raises — all errors are captured into the returned
        ``ConnectionTestResult.error_detail`` field.

        Preconditions:
          - ``connect()`` has been called at least once.

        Guarantees:
          - Always returns ``ConnectionTestResult``.
          - ``success=True`` when the provider responds.
          - ``success=False`` with ``error_detail`` otherwise.
          - ``latency_ms`` measures round-trip time.

        Errors raised: None.

        Errors silenced:
          - ALL — network, auth, and provider errors are caught and
            reflected in ``ConnectionTestResult(success=False, ...)``.
        """

    @abc.abstractmethod
    async def get_available_destinations(self) -> list[Destination]:
        """List channels and DM targets available to the bot.

        Preconditions:
          - Adapter is connected with at least ``channels:read`` scope.

        Guarantees:
          - Returns ``list[Destination]`` (may be empty).
          - Archived channels and inaccessible private channels excluded.

        Errors raised:
          - ``ChannelAuthError`` on token failure during enumeration.
          - ``ChannelConnectionError`` on network failure.

        Errors silenced:
          - Private channels where bot is not a member.
          - Archived channels.
        """
