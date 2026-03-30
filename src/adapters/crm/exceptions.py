"""CRM adapter exception hierarchy.

All exceptions carry an optional ``original_error`` attribute so callers can
inspect the underlying SDK error without coupling to HubSpot-specific types.
"""


class CRMAdapterError(Exception):
    """Base exception for all CRM adapter operations."""

    original_error: Exception | None

    def __init__(self, message: str, *, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class CRMAuthError(CRMAdapterError):
    """Token invalid, revoked, or missing required scope (HTTP 401)."""


class CRMRateLimitError(CRMAdapterError):
    """HTTP 429 from HubSpot. retry_after_seconds from Retry-After header."""

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


class CRMConnectionError(CRMAdapterError):
    """Network failure, DNS error, API timeout, or 5xx server error."""


class DuplicateContactError(CRMAdapterError):
    """Attempt to create a contact with an email that already exists (HTTP 409)."""


class ContactNotFoundError(CRMAdapterError):
    """Referenced contact_id does not exist in HubSpot (HTTP 404)."""


class FieldNotFoundError(CRMAdapterError):
    """Property does not exist in HubSpot schema (HTTP 400 PROPERTY_DOESNT_EXIST).

    Silenced in ``update_field`` per Sec 6.4 — exposed so callers can catch it
    if they need to know the field was skipped.
    """
