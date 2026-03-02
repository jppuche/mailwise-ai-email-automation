"""EmailAdapter ABC — provider-agnostic email interface.

contract-docstrings:
  Invariants: Adapter must be connected (via ``connect()``) before any
    operation except ``test_connection()``.
  Guarantees: All returned values are fully typed (no raw dicts cross the
    boundary). Deduplication is the *calling service's* responsibility.
  Errors raised: Typed exceptions from ``adapters.email.exceptions``.
  Errors silenced: Only ``test_connection()`` silences errors.
  External state: Email provider API (Gmail, etc.).
"""

from __future__ import annotations

import abc
from datetime import datetime

from src.adapters.email.schemas import (
    ConnectionStatus,
    ConnectionTestResult,
    DraftId,
    EmailCredentials,
    EmailMessage,
    Label,
)


class EmailAdapter(abc.ABC):
    """Abstract base for email provider adapters.

    Implementations must handle OAuth2 credentials, API pagination, MIME
    parsing, and structured error mapping. The adapter boundary is the
    typed schemas in ``adapters.email.schemas`` — raw provider dicts never
    leak past this layer.

    Deduplication (avoiding re-processing the same ``gmail_message_id``) is
    the calling service's responsibility, not the adapter's.

    Design note — sync interface:
      Unlike ChannelAdapter, CRMAdapter, and LLMAdapter (which are async),
      EmailAdapter methods are synchronous because the underlying Google
      API client (``google-api-python-client``) is sync-only. The calling
      service (``IngestionService``) wraps calls with
      ``asyncio.to_thread()`` when needed. This avoids double-wrapping
      at both the ABC and implementation levels.
    """

    @abc.abstractmethod
    def connect(self, credentials: EmailCredentials) -> ConnectionStatus:
        """Establish a connection to the email provider.

        Invariants:
          - ``credentials`` has non-empty ``client_id``, ``client_secret``,
            ``token``, and ``refresh_token``.

        Guarantees:
          - On success, the adapter is ready for subsequent operations.
          - Returns ``ConnectionStatus`` with ``connected=True`` and the
            authenticated account email.

        Errors raised:
          - ``ValueError`` if a required credential field is empty.
          - ``AuthError`` if the provider rejects the credentials.

        Errors silenced: None.
        """

    @abc.abstractmethod
    def fetch_new_messages(self, since: datetime, limit: int) -> list[EmailMessage]:
        """Fetch messages received after *since*, up to *limit*.

        Gmail API's ``messages.list`` returns message IDs. Each result is
        fetched individually via ``messages.get(format='full')`` to obtain
        the complete MIME payload. Parse failures on individual messages are
        logged and skipped — the caller can detect skips when
        ``len(result) < expected``.

        Invariants:
          - ``since`` is a timezone-aware ``datetime``.
          - ``limit`` is in the range ``[1, 500]``.
          - Adapter is connected.

        Guarantees:
          - Returns ``list[EmailMessage]`` (may be empty).
          - Each ``EmailMessage.received_at`` is timezone-aware UTC.
          - Each ``EmailMessage.gmail_message_id`` is populated.

        Errors raised:
          - ``ValueError`` if ``since`` is naive or ``limit`` is out of range.
          - ``AuthError`` on 401 or token refresh failure.
          - ``RateLimitError`` on 429.
          - ``EmailConnectionError`` on 5xx / network failure.
          - ``FetchError`` on other provider errors.

        Errors silenced:
          - Individual message parse failures (``KeyError``, ``ValueError``,
            ``ValidationError``) are logged with ``message_id`` and skipped.
        """

    @abc.abstractmethod
    def mark_as_processed(self, message_id: str) -> None:
        """Mark a message as processed on the provider.

        Typically adds a ``PROCESSED`` label and removes ``UNREAD``.

        Invariants:
          - ``message_id`` is a non-empty provider message ID.
          - Adapter is connected.

        Guarantees:
          - The message is marked on the provider side.

        Errors raised:
          - ``ValueError`` if ``message_id`` is empty.
          - ``AuthError``, ``RateLimitError``, ``EmailConnectionError``.

        Errors silenced: None.
        """

    @abc.abstractmethod
    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
    ) -> DraftId:
        """Create a draft email on the provider.

        Builds a MIME message with the given fields. When ``in_reply_to`` is
        provided, adds ``In-Reply-To`` and ``References`` headers so the
        provider threads the draft correctly.

        Invariants:
          - ``to`` contains an ``@`` character (basic RFC 5322 check).
          - ``body`` is non-empty.
          - Adapter is connected.

        Guarantees:
          - Returns a ``DraftId`` referencing the created draft.

        Errors raised:
          - ``ValueError`` if ``to`` or ``body`` violates preconditions.
          - ``AuthError``, ``RateLimitError``, ``EmailConnectionError``.
          - ``DraftCreationError`` on provider-specific draft failure.

        Errors silenced: None.
        """

    @abc.abstractmethod
    def get_labels(self) -> list[Label]:
        """List all labels/folders from the provider.

        Invariants:
          - Adapter is connected.

        Guarantees:
          - Returns ``list[Label]`` (may be empty).
          - Each ``Label`` has ``id``, ``name``, and ``type``.

        Errors raised:
          - ``EmailAdapterError`` if not connected.
          - ``AuthError``, ``EmailConnectionError``.

        Errors silenced: None.
        """

    @abc.abstractmethod
    def apply_label(self, message_id: str, label_id: str) -> None:
        """Apply a label to a message on the provider.

        Invariants:
          - ``message_id`` and ``label_id`` are non-empty strings.
          - Adapter is connected.

        Guarantees:
          - The label is applied on the provider side.

        Errors raised:
          - ``ValueError`` if ``message_id`` or ``label_id`` is empty.
          - ``AuthError``, ``RateLimitError``, ``LabelError``.

        Errors silenced: None.
        """

    @abc.abstractmethod
    def test_connection(self) -> ConnectionTestResult:
        """Non-destructive connectivity check (health-check semantics).

        This method NEVER raises — all errors are captured into the returned
        ``ConnectionTestResult.error`` field.

        Invariants:
          - Credentials have been loaded (adapter initialised via ``connect``
            or equivalent setup).

        Guarantees:
          - Always returns ``ConnectionTestResult``.
          - ``connected=True`` when the provider responds successfully.
          - ``connected=False`` with ``error`` message otherwise.

        Errors raised: None.

        Errors silenced:
          - ALL — network, auth, and provider errors are caught and
            reflected in ``ConnectionTestResult(connected=False, error=...)``.
        """
