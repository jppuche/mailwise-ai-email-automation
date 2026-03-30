"""Email adapter exception hierarchy.

All exceptions carry an optional ``original_error`` attribute so callers can
inspect the underlying SDK error without coupling to Google-specific types.
"""


class EmailAdapterError(Exception):
    """Base exception for all email adapter operations."""

    original_error: Exception | None

    def __init__(self, message: str, *, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class AuthError(EmailAdapterError):
    """OAuth2 credentials invalid, expired, or revoked (HTTP 401 / RefreshError)."""


class RateLimitError(EmailAdapterError):
    """Provider rate limit exceeded (HTTP 429)."""


class EmailConnectionError(EmailAdapterError):
    """Provider server error or network failure (HTTP 5xx)."""


class FetchError(EmailAdapterError):
    """Generic fetch failure not covered by more specific types."""


class DraftCreationError(EmailAdapterError):
    """Failed to create a draft message on the provider."""


class LabelError(EmailAdapterError):
    """Failed to list or apply a label on the provider."""
