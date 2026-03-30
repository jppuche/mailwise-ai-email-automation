"""Channel adapter exception hierarchy.

All exceptions carry an optional ``original_error`` attribute so callers can
inspect the underlying SDK error without coupling to Slack-specific types.
"""


class ChannelAdapterError(Exception):
    """Base exception for all channel adapter operations."""

    original_error: Exception | None

    def __init__(self, message: str, *, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class ChannelAuthError(ChannelAdapterError):
    """Token invalid, revoked, or missing required scope."""


class ChannelRateLimitError(ChannelAdapterError):
    """HTTP 429 from Slack. retry_after_seconds from Retry-After header."""

    retry_after_seconds: int | None

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: int | None = None,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message, original_error=original_error)
        self.retry_after_seconds = retry_after_seconds


class ChannelConnectionError(ChannelAdapterError):
    """Network failure, DNS error, or API timeout."""


class ChannelDeliveryError(ChannelAdapterError):
    """Channel not found, archived, bot not in channel, etc."""
