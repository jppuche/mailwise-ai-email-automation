"""CRMAdapter ABC — provider-agnostic CRM interface.

contract-docstrings:
  Invariants: Adapter must be connected (via ``connect()``) before any
    operation except ``test_connection()``.
  Guarantees: All returned values are fully typed (no raw dicts cross the
    boundary). SDK objects never leak past the adapter layer.
  Errors raised: Typed exceptions from ``adapters.crm.exceptions``.
  Errors silenced: ``test_connection()`` silences all errors.
    ``update_field()`` silences ``FieldNotFoundError`` per Sec 6.4.
  External state: CRM provider API (HubSpot, etc.).

try-except D7: External-state operations use structured try/except with
  specific exception types mapped to domain exceptions.
"""

from __future__ import annotations

import abc

from src.adapters.crm.schemas import (
    ActivityData,
    ActivityId,
    ConnectionStatus,
    ConnectionTestResult,
    Contact,
    CreateContactData,
    CreateLeadData,
    CRMCredentials,
    LeadId,
)


class CRMAdapter(abc.ABC):
    """Abstract base for CRM adapters.

    Implementations must handle API authentication, data extraction from
    SDK responses, and structured error mapping. The adapter boundary is the
    typed schemas in ``adapters.crm.schemas`` — raw provider objects never
    leak past this layer.
    """

    @abc.abstractmethod
    async def connect(self, credentials: CRMCredentials) -> ConnectionStatus:
        """Establish a connection to the CRM provider.

        Preconditions:
          - ``credentials.access_token`` is non-empty (Private App Token).

        Guarantees:
          - On success, adapter is ready for subsequent operations.
          - Returns ``ConnectionStatus`` with ``connected=True``.

        Errors raised:
          - ``ValueError`` if ``access_token`` is empty.
          - ``CRMAuthError`` if the provider rejects the token (HTTP 401).
          - ``CRMConnectionError`` on network / timeout / DNS failure.

        Errors silenced: None.
        """

    @abc.abstractmethod
    async def lookup_contact(self, email: str) -> Contact | None:
        """Look up a contact by email address.

        Preconditions:
          - ``email`` is non-empty and contains '@'.
          - Adapter is connected.

        Guarantees:
          - Returns ``Contact`` if found, ``None`` if no match.
          - On multiple matches, returns the most recent by ``createdate``.

        Errors raised:
          - ``ValueError`` if ``email`` is empty or missing '@'.
          - ``CRMAuthError`` on token failure (HTTP 401).
          - ``CRMRateLimitError`` on HTTP 429.
          - ``CRMConnectionError`` on network / timeout failure.

        Errors silenced:
          - Multiple matches: uses the most recent contact, logs ambiguity
            with ``contact_count``. Caller does not detect ambiguity.
        """

    @abc.abstractmethod
    async def create_contact(self, data: CreateContactData) -> Contact:
        """Create a new contact in the CRM.

        Preconditions:
          - ``data.email`` is non-empty and contains '@'.
          - Adapter is connected.

        Guarantees:
          - Returns the created ``Contact`` with its CRM-assigned ``id``.

        Errors raised:
          - ``ValueError`` if ``data.email`` is empty or invalid.
          - ``CRMAuthError`` on token failure (HTTP 401).
          - ``CRMRateLimitError`` on HTTP 429.
          - ``DuplicateContactError`` if email already exists (HTTP 409).
          - ``CRMConnectionError`` on network failure.

        Errors silenced: None.
        """

    @abc.abstractmethod
    async def log_activity(self, contact_id: str, activity: ActivityData) -> ActivityId:
        """Log an email activity (note) associated with a contact.

        Preconditions:
          - ``contact_id`` is non-empty (numeric HubSpot ID as str).
          - ``activity.subject`` is non-empty.
          - ``activity.timestamp`` is timezone-aware.
          - ``activity.snippet`` is pre-truncated by the calling service.
          - Adapter is connected.

        Guarantees:
          - Returns ``ActivityId`` of the created note.

        Errors raised:
          - ``ValueError`` if ``contact_id`` is empty.
          - ``CRMAuthError`` on token failure (HTTP 401).
          - ``CRMRateLimitError`` on HTTP 429.
          - ``ContactNotFoundError`` if ``contact_id`` does not exist (HTTP 404).
          - ``CRMConnectionError`` on network failure.

        Errors silenced: None.
        """

    @abc.abstractmethod
    async def create_lead(self, data: CreateLeadData) -> LeadId:
        """Create a lead (deal) in the CRM linked to an existing contact.

        Preconditions:
          - ``data.contact_id`` is non-empty.
          - ``data.summary`` is non-empty.
          - ``data.source`` is non-empty.
          - Adapter is connected.

        Guarantees:
          - Returns ``LeadId`` of the created deal.

        Errors raised:
          - ``ValueError`` if ``contact_id``, ``summary``, or ``source`` is empty.
          - ``CRMAuthError`` on token failure (HTTP 401).
          - ``CRMRateLimitError`` on HTTP 429.
          - ``ContactNotFoundError`` if ``contact_id`` does not exist (HTTP 404).
          - ``CRMConnectionError`` on network failure.

        Errors silenced: None.
        """

    @abc.abstractmethod
    async def update_field(self, contact_id: str, field: str, value: str) -> None:
        """Update a single property on a contact.

        Preconditions:
          - ``contact_id`` is non-empty.
          - ``field`` is non-empty (HubSpot property name).
          - ``value`` may be empty (clearing a field is valid).
          - Adapter is connected.

        Guarantees:
          - On success, the field is updated in the CRM.

        Errors raised:
          - ``ValueError`` if ``contact_id`` or ``field`` is empty.
          - ``CRMAuthError`` on token failure (HTTP 401).
          - ``CRMRateLimitError`` on HTTP 429.
          - ``ContactNotFoundError`` if ``contact_id`` does not exist (HTTP 404).
          - ``CRMConnectionError`` on network failure.

        Errors silenced:
          - ``FieldNotFoundError``: property does not exist in HubSpot schema
            (HTTP 400 + PROPERTY_DOESNT_EXIST). Logged with ``field`` name
            and ``contact_id``, then skipped per Sec 6.4.
        """

    @abc.abstractmethod
    async def test_connection(self) -> ConnectionTestResult:
        """Non-destructive connectivity check (health-check semantics).

        This method NEVER raises — all errors are captured into the returned
        ``ConnectionTestResult.error_detail`` field.

        Preconditions:
          - Adapter initialized with credentials (``connect()`` need not
            have completed successfully).

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
