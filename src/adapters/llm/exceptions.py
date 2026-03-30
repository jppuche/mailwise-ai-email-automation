"""LLM adapter exception hierarchy.

All exceptions carry an optional ``original_error`` attribute so callers can
inspect the underlying SDK error without coupling to LiteLLM-specific types.
"""


class LLMAdapterError(Exception):
    """Base exception for all LLM adapter operations."""

    original_error: Exception | None

    def __init__(self, message: str, *, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class LLMConnectionError(LLMAdapterError):
    """LLM provider unreachable (network, DNS, incorrect endpoint)."""


class LLMRateLimitError(LLMAdapterError):
    """Provider returned 429. retry_after_seconds may be None."""

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


class LLMTimeoutError(LLMAdapterError):
    """Call exceeded LLM_TIMEOUT_SECONDS."""


class OutputParseError(LLMAdapterError):
    """LLM output could not be parsed to ClassificationResult.

    Internal only — the adapter applies fallback, never re-raises this.
    """

    raw_output: str

    def __init__(
        self,
        message: str,
        *,
        raw_output: str,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message, original_error=original_error)
        self.raw_output = raw_output
