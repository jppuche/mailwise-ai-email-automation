"""HubSpotAdapter — concrete CRMAdapter using hubspot-api-client SDK.

Invariants: ``CRMCredentials`` must be provided via ``connect()``
  before any operation except ``test_connection()``.
Guarantees: Raw SDK objects (``SimplePublicObject``, ``ApiException``)
  never escape this module. All returns are typed adapter schemas.
Errors raised: Typed ``CRMAdapterError`` subclasses.
Errors silenced: ``test_connection()`` silences all errors.
  ``update_field()`` silences ``FieldNotFoundError`` per Sec 6.4.
External state: HubSpot API via hubspot-api-client SDK (sync).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import time
from datetime import datetime

import hubspot
import structlog
from hubspot.crm.contacts.exceptions import ApiException

from src.adapters.crm.base import CRMAdapter
from src.adapters.crm.exceptions import (
    ContactNotFoundError,
    CRMAuthError,
    CRMConnectionError,
    CRMRateLimitError,
    DuplicateContactError,
    FieldNotFoundError,
)
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
from src.core.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Module-level helpers (not methods — stateless classification)
# ---------------------------------------------------------------------------


def _raise_from_hubspot_exc(exc: ApiException) -> None:
    """Classify ApiException by HTTP status and re-raise as domain exception.

    Local computation — conditional on ``exc.status``, no nested try/except.
    """
    if exc.status == 401:
        raise CRMAuthError(f"HubSpot auth error: {exc.reason}", original_error=exc) from exc
    if exc.status == 404:
        raise ContactNotFoundError(f"Contact not found: {exc.reason}", original_error=exc) from exc
    if exc.status == 409:
        raise DuplicateContactError(
            f"Contact already exists: {exc.reason}", original_error=exc
        ) from exc
    if exc.status == 429:
        retry_after: int | None = None
        with contextlib.suppress(ValueError, TypeError):
            retry_after = int(exc.headers.get("Retry-After", 0)) if exc.headers else None
        raise CRMRateLimitError(
            "HubSpot rate limit exceeded",
            retry_after_seconds=retry_after,
            original_error=exc,
        ) from exc
    if exc.status == 400 and "PROPERTY_DOESNT_EXIST" in (exc.body or ""):
        raise FieldNotFoundError(f"Property not found: {exc.reason}", original_error=exc) from exc
    raise CRMConnectionError(
        f"HubSpot API error {exc.status}: {exc.reason}", original_error=exc
    ) from exc


def _hash_email(email: str) -> str:
    """SHA-256 hash of email for PII-safe logging."""
    return hashlib.sha256(email.encode()).hexdigest()[:16]


def _parse_hs_datetime(value: str | None) -> datetime | None:
    """Parse HubSpot timestamp string to timezone-aware datetime.

    Local computation — conditional, no try/except.
    """
    if not value:
        return None
    # HubSpot uses ISO 8601 with milliseconds (e.g. "2024-01-15T10:30:00.000Z")
    with contextlib.suppress(ValueError):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


class HubSpotAdapter(CRMAdapter):
    """HubSpot CRM adapter using hubspot-api-client SDK.

    The SDK is sync-only — all calls are wrapped with
    ``asyncio.to_thread()`` for async compatibility.
    """

    def __init__(self) -> None:
        self._client: hubspot.HubSpot | None = None
        self._connected: bool = False
        self._access_token: str = ""

    # -- Private helpers ---------------------------------------------------

    def _ensure_connected(self) -> None:
        """Verify adapter is connected; raise CRMAuthError if not."""
        if not self._connected or self._client is None:
            raise CRMAuthError("Adapter not connected — call connect() first")

    # -- Public interface (CRMAdapter ABC) ---------------------------------

    async def connect(self, credentials: CRMCredentials) -> ConnectionStatus:
        if not credentials.access_token:
            raise ValueError("credentials.access_token must not be empty")

        client = hubspot.HubSpot(access_token=credentials.access_token)

        try:
            await asyncio.to_thread(
                client.crm.contacts.basic_api.get_page,
                limit=1,
            )
        except ApiException as exc:
            if exc.status == 401:
                return ConnectionStatus(
                    connected=False,
                    error=f"Authentication failed: {exc.reason}",
                )
            raise CRMConnectionError(
                f"HubSpot connection error: {exc.reason}", original_error=exc
            ) from exc
        except Exception as exc:  # noqa: BLE001 — connect surfaces failure via status
            return ConnectionStatus(
                connected=False,
                error=f"Connection failed: {exc}",
            )

        self._client = client
        self._connected = True
        self._access_token = credentials.access_token

        logger.info("crm_connected", provider="hubspot")

        return ConnectionStatus(connected=True)

    async def lookup_contact(self, email: str) -> Contact | None:
        if not email or "@" not in email:
            raise ValueError(f"Invalid email format: {email!r}")
        self._ensure_connected()
        assert self._client is not None  # narrowed by _ensure_connected

        try:
            response = await asyncio.to_thread(
                self._client.crm.contacts.search_api.do_search,
                public_object_search_request={
                    "filterGroups": [
                        {
                            "filters": [
                                {
                                    "propertyName": "email",
                                    "operator": "EQ",
                                    "value": email,
                                }
                            ]
                        }
                    ],
                    "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
                    "limit": 2,  # detect ambiguity
                },
            )
        except ApiException as exc:
            _raise_from_hubspot_exc(exc)

        results = response.results
        if not results:
            return None

        if len(results) > 1:
            logger.warning(
                "crm_duplicate_contacts",
                email_hash=_hash_email(email),
                contact_count=len(results),
            )

        raw = results[0]
        props = raw.properties
        return Contact(
            id=raw.id,
            email=props.get("email", ""),
            first_name=props.get("firstname"),
            last_name=props.get("lastname"),
            company=props.get("company"),
            created_at=_parse_hs_datetime(props.get("createdate")),
            updated_at=_parse_hs_datetime(props.get("lastmodifieddate")),
        )

    async def create_contact(self, data: CreateContactData) -> Contact:
        self._ensure_connected()
        assert self._client is not None  # narrowed by _ensure_connected

        properties: dict[str, str] = {"email": data.email}
        if data.first_name:
            properties["firstname"] = data.first_name
        if data.last_name:
            properties["lastname"] = data.last_name
        if data.company:
            properties["company"] = data.company
        if data.source:
            properties["hs_lead_status"] = data.source

        try:
            response = await asyncio.to_thread(
                self._client.crm.contacts.basic_api.create,
                simple_public_object_input_for_create={"properties": properties},
            )
        except ApiException as exc:
            _raise_from_hubspot_exc(exc)

        logger.info("crm_contact_created", contact_id=response.id)

        props = response.properties
        return Contact(
            id=response.id,
            email=props.get("email", data.email),
            first_name=props.get("firstname"),
            last_name=props.get("lastname"),
            company=props.get("company"),
            created_at=_parse_hs_datetime(props.get("createdate")),
            updated_at=_parse_hs_datetime(props.get("lastmodifieddate")),
        )

    async def log_activity(self, contact_id: str, activity: ActivityData) -> ActivityId:
        if not contact_id:
            raise ValueError("contact_id must not be empty")
        self._ensure_connected()
        assert self._client is not None  # narrowed by _ensure_connected

        note_body = (
            f"Action: {activity.classification_action} | "
            f"Type: {activity.classification_type}\n"
            f"Email ID: {activity.email_id}\n"
            f"Snippet: {activity.snippet}"
        )
        if activity.dashboard_link:
            note_body += f"\nDashboard: {activity.dashboard_link}"

        hs_timestamp = str(int(activity.timestamp.timestamp() * 1000))

        try:
            note_response = await asyncio.to_thread(
                self._client.crm.objects.notes.basic_api.create,
                simple_public_object_input_for_create={
                    "properties": {
                        "hs_note_body": note_body,
                        "hs_timestamp": hs_timestamp,
                    }
                },
            )
        except ApiException as exc:
            _raise_from_hubspot_exc(exc)

        note_id = note_response.id

        try:
            await asyncio.to_thread(
                self._client.crm.objects.notes.associations_api.create,
                note_id=note_id,
                to_object_type="contacts",
                to_object_id=contact_id,
                association_type=[
                    {
                        "associationCategory": "HUBSPOT_DEFINED",
                        "associationTypeId": 202,
                    }
                ],
            )
        except ApiException as exc:
            _raise_from_hubspot_exc(exc)

        logger.info(
            "crm_activity_logged",
            contact_id=contact_id,
            note_id=note_id,
            email_id=activity.email_id,
        )

        return ActivityId(note_id)

    async def create_lead(self, data: CreateLeadData) -> LeadId:
        if not data.contact_id:
            raise ValueError("contact_id must not be empty")
        if not data.summary:
            raise ValueError("summary must not be empty")
        if not data.source:
            raise ValueError("source must not be empty")
        self._ensure_connected()
        assert self._client is not None  # narrowed by _ensure_connected

        settings = get_settings()
        deal_properties: dict[str, str] = {
            "dealname": f"Lead from {data.source}: {data.summary[:80]}",
            "dealstage": "appointmentscheduled",  # HubSpot default pipeline first stage
            "hs_lead_status": data.lead_status or settings.hubspot_default_lead_status,
            "description": data.summary,
        }

        try:
            response = await asyncio.to_thread(
                self._client.crm.deals.basic_api.create,
                simple_public_object_input_for_create={
                    "properties": deal_properties,
                },
            )
        except ApiException as exc:
            _raise_from_hubspot_exc(exc)

        deal_id = response.id

        try:
            await asyncio.to_thread(
                self._client.crm.deals.associations_api.create,
                deal_id=deal_id,
                to_object_type="contacts",
                to_object_id=data.contact_id,
                association_type=[
                    {
                        "associationCategory": "HUBSPOT_DEFINED",
                        "associationTypeId": 3,  # deal-to-contact
                    }
                ],
            )
        except ApiException as exc:
            _raise_from_hubspot_exc(exc)

        logger.info(
            "crm_lead_created",
            deal_id=deal_id,
            contact_id=data.contact_id,
        )

        return LeadId(deal_id)

    async def update_field(self, contact_id: str, field: str, value: str) -> None:
        if not contact_id:
            raise ValueError("contact_id must not be empty")
        if not field:
            raise ValueError("field must not be empty")
        self._ensure_connected()
        assert self._client is not None  # narrowed by _ensure_connected

        try:
            await asyncio.to_thread(
                self._client.crm.contacts.basic_api.update,
                contact_id=contact_id,
                simple_public_object_input={"properties": {field: value}},
            )
        except ApiException as exc:
            # FieldNotFoundError silenced per Sec 6.4 (log, skip, no fail)
            if exc.status == 400 and "PROPERTY_DOESNT_EXIST" in (exc.body or ""):
                logger.warning(
                    "crm_field_not_found",
                    contact_id=contact_id,
                    field=field,
                )
                return
            _raise_from_hubspot_exc(exc)

        logger.info(
            "crm_field_updated",
            contact_id=contact_id,
            field=field,
        )

    async def test_connection(self) -> ConnectionTestResult:
        if self._client is None:
            return ConnectionTestResult(
                success=False,
                latency_ms=0,
                error_detail="Adapter not initialized — credentials not loaded",
            )

        start = time.monotonic()
        try:
            await asyncio.to_thread(
                self._client.crm.contacts.basic_api.get_page,
                limit=1,
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            return ConnectionTestResult(
                success=True,
                latency_ms=latency_ms,
            )
        except Exception as exc:  # noqa: BLE001 — health-check silences ALL errors
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.warning("crm_test_connection_failed", error=str(exc))
            return ConnectionTestResult(
                success=False,
                latency_ms=latency_ms,
                error_detail=str(exc),
            )
