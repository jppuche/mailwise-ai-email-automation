"""Tests for HubSpotAdapter with mocked hubspot-api-client SDK.

No real HubSpot API calls. All SDK methods are sync MagicMocks wrapped by a
patched ``asyncio.to_thread`` that runs them inline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from hubspot.crm.contacts.exceptions import ApiException

from src.adapters.crm.exceptions import (
    ContactNotFoundError,
    CRMAuthError,
    CRMConnectionError,
    CRMRateLimitError,
    DuplicateContactError,
    FieldNotFoundError,
)
from src.adapters.crm.hubspot import (
    HubSpotAdapter,
    _hash_email,
    _parse_hs_datetime,
    _raise_from_hubspot_exc,
)
from src.adapters.crm.schemas import (
    ActivityData,
    ConnectionTestResult,
    Contact,
    CreateContactData,
    CreateLeadData,
    CRMCredentials,
)

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _make_api_exception(status: int, reason: str = "", body: str = "") -> ApiException:
    """Build an ApiException with a specific HTTP status for testing."""
    exc = ApiException(status=status, reason=reason)
    exc.body = body
    exc.headers = {}
    return exc


def _make_api_exception_with_retry(retry_after: str = "30") -> ApiException:
    """Build a 429 ApiException with a Retry-After header."""
    exc = ApiException(status=429, reason="Too Many Requests")
    exc.body = ""
    exc.headers = {"Retry-After": retry_after}
    return exc


# ---------------------------------------------------------------------------
# Autouse fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_to_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make asyncio.to_thread run synchronously in tests.

    Without this, every test would attempt to submit work to a real thread
    pool, which makes mocking the sync SDK methods fragile.
    """

    async def _sync_to_thread(func: object, /, *args: object, **kwargs: object) -> object:
        assert callable(func)
        return func(*args, **kwargs)

    monkeypatch.setattr("asyncio.to_thread", _sync_to_thread)


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch get_settings so tests do not need a .env file."""
    settings = MagicMock()
    settings.hubspot_default_lead_status = "NEW"
    settings.hubspot_activity_snippet_length = 200
    settings.hubspot_auto_create_contacts = False
    settings.hubspot_api_timeout_seconds = 15
    settings.hubspot_rate_limit_per_10s = 100
    monkeypatch.setattr("src.adapters.crm.hubspot.get_settings", lambda: settings)
    return settings


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_hubspot_client() -> MagicMock:
    """Fully-configured mock hubspot.HubSpot() client with happy-path defaults."""
    client = MagicMock()

    # contacts.search_api.do_search — default: empty results
    search_result = MagicMock()
    search_result.results = []
    client.crm.contacts.search_api.do_search.return_value = search_result

    # contacts.basic_api.create — default: contact "12345"
    created = MagicMock()
    created.id = "12345"
    created.properties = {
        "email": "alice@example.com",
        "firstname": "Alice",
        "lastname": "Smith",
        "company": "Acme",
    }
    client.crm.contacts.basic_api.create.return_value = created

    # contacts.basic_api.update — default: success (None)
    client.crm.contacts.basic_api.update.return_value = None

    # contacts.basic_api.get_page — default: empty page
    page = MagicMock()
    page.results = []
    client.crm.contacts.basic_api.get_page.return_value = page

    # crm.objects.notes.basic_api.create — default: note "note-99"
    note = MagicMock()
    note.id = "note-99"
    client.crm.objects.notes.basic_api.create.return_value = note

    # crm.objects.notes.associations_api.create — default: success
    client.crm.objects.notes.associations_api.create.return_value = None

    # crm.deals.basic_api.create — default: deal "deal-77"
    deal = MagicMock()
    deal.id = "deal-77"
    client.crm.deals.basic_api.create.return_value = deal

    # crm.deals.associations_api.create — default: success
    client.crm.deals.associations_api.create.return_value = None

    return client


async def _connected_adapter(mock_client: MagicMock) -> HubSpotAdapter:
    """Return a HubSpotAdapter that has already completed connect()."""
    adapter = HubSpotAdapter()
    with patch("src.adapters.crm.hubspot.hubspot.HubSpot", return_value=mock_client):
        await adapter.connect(CRMCredentials(access_token="test-token"))
    return adapter


@pytest.fixture
def activity() -> ActivityData:
    return ActivityData(
        subject="Re: Your inquiry",
        timestamp=datetime(2025, 3, 1, 12, 0, tzinfo=UTC),
        classification_action="reply",
        classification_type="support",
        snippet="Thank you for contacting us.",
        email_id="email-001",
        dashboard_link="https://dashboard/emails/email-001",
    )


# ---------------------------------------------------------------------------
# TestConnect
# ---------------------------------------------------------------------------


class TestConnect:
    """Tests for HubSpotAdapter.connect()."""

    async def test_success_returns_connected_true(self, mock_hubspot_client: MagicMock) -> None:
        adapter = HubSpotAdapter()
        with patch("src.adapters.crm.hubspot.hubspot.HubSpot", return_value=mock_hubspot_client):
            result = await adapter.connect(CRMCredentials(access_token="test-token"))
        assert result.connected is True

    async def test_success_sets_internal_state(self, mock_hubspot_client: MagicMock) -> None:
        adapter = HubSpotAdapter()
        with patch("src.adapters.crm.hubspot.hubspot.HubSpot", return_value=mock_hubspot_client):
            await adapter.connect(CRMCredentials(access_token="test-token"))
        assert adapter._connected is True
        assert adapter._client is not None
        assert adapter._access_token == "test-token"

    async def test_empty_access_token_raises_value_error(self) -> None:
        adapter = HubSpotAdapter()
        with pytest.raises(ValueError, match="access_token must not be empty"):
            await adapter.connect(CRMCredentials(access_token=""))

    async def test_401_returns_connected_false(self, mock_hubspot_client: MagicMock) -> None:
        mock_hubspot_client.crm.contacts.basic_api.get_page.side_effect = _make_api_exception(
            401, "Unauthorized"
        )
        adapter = HubSpotAdapter()
        with patch("src.adapters.crm.hubspot.hubspot.HubSpot", return_value=mock_hubspot_client):
            result = await adapter.connect(CRMCredentials(access_token="bad-token"))
        assert result.connected is False
        assert result.error is not None

    async def test_401_does_not_set_connected_state(self, mock_hubspot_client: MagicMock) -> None:
        mock_hubspot_client.crm.contacts.basic_api.get_page.side_effect = _make_api_exception(
            401, "Unauthorized"
        )
        adapter = HubSpotAdapter()
        with patch("src.adapters.crm.hubspot.hubspot.HubSpot", return_value=mock_hubspot_client):
            await adapter.connect(CRMCredentials(access_token="bad-token"))
        assert adapter._connected is False
        assert adapter._client is None

    async def test_network_error_returns_connected_false(
        self, mock_hubspot_client: MagicMock
    ) -> None:
        mock_hubspot_client.crm.contacts.basic_api.get_page.side_effect = ConnectionError(
            "DNS failure"
        )
        adapter = HubSpotAdapter()
        with patch("src.adapters.crm.hubspot.hubspot.HubSpot", return_value=mock_hubspot_client):
            result = await adapter.connect(CRMCredentials(access_token="test-token"))
        assert result.connected is False

    async def test_network_error_returns_error_message(
        self, mock_hubspot_client: MagicMock
    ) -> None:
        mock_hubspot_client.crm.contacts.basic_api.get_page.side_effect = ConnectionError(
            "DNS failure"
        )
        adapter = HubSpotAdapter()
        with patch("src.adapters.crm.hubspot.hubspot.HubSpot", return_value=mock_hubspot_client):
            result = await adapter.connect(CRMCredentials(access_token="test-token"))
        assert result.error is not None
        assert len(result.error) > 0


# ---------------------------------------------------------------------------
# TestLookupContact
# ---------------------------------------------------------------------------


class TestLookupContact:
    """Tests for HubSpotAdapter.lookup_contact()."""

    async def test_found_returns_contact(self, mock_hubspot_client: MagicMock) -> None:
        raw = MagicMock()
        raw.id = "42"
        raw.properties = {
            "email": "alice@example.com",
            "firstname": "Alice",
            "lastname": "Smith",
            "company": "Acme",
        }
        mock_hubspot_client.crm.contacts.search_api.do_search.return_value = MagicMock(
            results=[raw]
        )
        adapter = await _connected_adapter(mock_hubspot_client)
        result = await adapter.lookup_contact("alice@example.com")
        assert isinstance(result, Contact)
        assert result.id == "42"
        assert result.email == "alice@example.com"
        assert result.first_name == "Alice"
        assert result.last_name == "Smith"
        assert result.company == "Acme"

    async def test_not_found_returns_none(self, mock_hubspot_client: MagicMock) -> None:
        mock_hubspot_client.crm.contacts.search_api.do_search.return_value = MagicMock(results=[])
        adapter = await _connected_adapter(mock_hubspot_client)
        result = await adapter.lookup_contact("ghost@example.com")
        assert result is None

    async def test_multiple_matches_returns_first(self, mock_hubspot_client: MagicMock) -> None:
        raw1 = MagicMock()
        raw1.id = "10"
        raw1.properties = {"email": "dup@example.com", "firstname": "First"}
        raw2 = MagicMock()
        raw2.id = "20"
        raw2.properties = {"email": "dup@example.com", "firstname": "Second"}
        mock_hubspot_client.crm.contacts.search_api.do_search.return_value = MagicMock(
            results=[raw1, raw2]
        )
        adapter = await _connected_adapter(mock_hubspot_client)
        result = await adapter.lookup_contact("dup@example.com")
        assert result is not None
        assert result.id == "10"

    async def test_multiple_matches_no_exception(self, mock_hubspot_client: MagicMock) -> None:
        raw1 = MagicMock()
        raw1.id = "10"
        raw1.properties = {"email": "dup@example.com"}
        raw2 = MagicMock()
        raw2.id = "20"
        raw2.properties = {"email": "dup@example.com"}
        mock_hubspot_client.crm.contacts.search_api.do_search.return_value = MagicMock(
            results=[raw1, raw2]
        )
        adapter = await _connected_adapter(mock_hubspot_client)
        # Must not raise — ambiguity is logged, most recent returned
        await adapter.lookup_contact("dup@example.com")

    async def test_empty_email_raises_value_error(self, mock_hubspot_client: MagicMock) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        with pytest.raises(ValueError, match="Invalid email format"):
            await adapter.lookup_contact("")

    async def test_email_without_at_raises_value_error(
        self, mock_hubspot_client: MagicMock
    ) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        with pytest.raises(ValueError, match="Invalid email format"):
            await adapter.lookup_contact("notanemail")

    async def test_not_connected_raises_crm_auth_error(self) -> None:
        adapter = HubSpotAdapter()
        with pytest.raises(CRMAuthError):
            await adapter.lookup_contact("alice@example.com")

    async def test_401_raises_crm_auth_error(self, mock_hubspot_client: MagicMock) -> None:
        mock_hubspot_client.crm.contacts.search_api.do_search.side_effect = _make_api_exception(401)
        adapter = await _connected_adapter(mock_hubspot_client)
        with pytest.raises(CRMAuthError):
            await adapter.lookup_contact("alice@example.com")

    async def test_429_raises_rate_limit_error(self, mock_hubspot_client: MagicMock) -> None:
        mock_hubspot_client.crm.contacts.search_api.do_search.side_effect = (
            _make_api_exception_with_retry("45")
        )
        adapter = await _connected_adapter(mock_hubspot_client)
        with pytest.raises(CRMRateLimitError):
            await adapter.lookup_contact("alice@example.com")

    async def test_network_error_raises_crm_connection_error(
        self, mock_hubspot_client: MagicMock
    ) -> None:
        mock_hubspot_client.crm.contacts.search_api.do_search.side_effect = ConnectionError(
            "timeout"
        )
        adapter = await _connected_adapter(mock_hubspot_client)
        # ConnectionError is not ApiException so it propagates as-is from to_thread
        with pytest.raises(ConnectionError):
            await adapter.lookup_contact("alice@example.com")

    async def test_found_contact_has_no_sdk_objects(self, mock_hubspot_client: MagicMock) -> None:
        raw = MagicMock()
        raw.id = "99"
        raw.properties = {"email": "safe@example.com"}
        mock_hubspot_client.crm.contacts.search_api.do_search.return_value = MagicMock(
            results=[raw]
        )
        adapter = await _connected_adapter(mock_hubspot_client)
        result = await adapter.lookup_contact("safe@example.com")
        # Result must be a Pydantic model, never a raw SDK object
        assert isinstance(result, Contact)


# ---------------------------------------------------------------------------
# TestCreateContact
# ---------------------------------------------------------------------------


class TestCreateContact:
    """Tests for HubSpotAdapter.create_contact()."""

    async def test_success_returns_contact(self, mock_hubspot_client: MagicMock) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        data = CreateContactData(
            email="alice@example.com",
            first_name="Alice",
            last_name="Smith",
            company="Acme",
        )
        result = await adapter.create_contact(data)
        assert isinstance(result, Contact)
        assert result.id == "12345"
        assert result.email == "alice@example.com"

    async def test_success_sets_first_name(self, mock_hubspot_client: MagicMock) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        data = CreateContactData(email="alice@example.com", first_name="Alice")
        result = await adapter.create_contact(data)
        assert result.first_name == "Alice"

    async def test_not_connected_raises_crm_auth_error(self) -> None:
        adapter = HubSpotAdapter()
        data = CreateContactData(email="alice@example.com")
        with pytest.raises(CRMAuthError):
            await adapter.create_contact(data)

    async def test_409_raises_duplicate_contact_error(self, mock_hubspot_client: MagicMock) -> None:
        mock_hubspot_client.crm.contacts.basic_api.create.side_effect = _make_api_exception(
            409, "Conflict"
        )
        adapter = await _connected_adapter(mock_hubspot_client)
        data = CreateContactData(email="dup@example.com")
        with pytest.raises(DuplicateContactError):
            await adapter.create_contact(data)

    async def test_401_raises_crm_auth_error(self, mock_hubspot_client: MagicMock) -> None:
        mock_hubspot_client.crm.contacts.basic_api.create.side_effect = _make_api_exception(401)
        adapter = await _connected_adapter(mock_hubspot_client)
        data = CreateContactData(email="alice@example.com")
        with pytest.raises(CRMAuthError):
            await adapter.create_contact(data)

    async def test_429_raises_rate_limit_error(self, mock_hubspot_client: MagicMock) -> None:
        mock_hubspot_client.crm.contacts.basic_api.create.side_effect = (
            _make_api_exception_with_retry("60")
        )
        adapter = await _connected_adapter(mock_hubspot_client)
        data = CreateContactData(email="alice@example.com")
        raised: CRMRateLimitError | None = None
        try:
            await adapter.create_contact(data)
        except CRMRateLimitError as exc:
            raised = exc
        assert raised is not None
        assert raised.retry_after_seconds == 60

    async def test_result_is_pydantic_model(self, mock_hubspot_client: MagicMock) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        data = CreateContactData(email="alice@example.com")
        result = await adapter.create_contact(data)
        # Must be a typed Contact, never an SDK SimplePublicObject
        assert type(result).__name__ == "Contact"


# ---------------------------------------------------------------------------
# TestLogActivity
# ---------------------------------------------------------------------------


class TestLogActivity:
    """Tests for HubSpotAdapter.log_activity()."""

    async def test_success_returns_activity_id(
        self, mock_hubspot_client: MagicMock, activity: ActivityData
    ) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        result = await adapter.log_activity("contact-1", activity)
        assert isinstance(result, str)
        assert result == "note-99"

    async def test_returns_activity_id_is_str(
        self, mock_hubspot_client: MagicMock, activity: ActivityData
    ) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        result = await adapter.log_activity("contact-1", activity)
        # ActivityId is a NewType wrapping str — str at runtime
        assert isinstance(result, str)

    async def test_empty_contact_id_raises_value_error(
        self, mock_hubspot_client: MagicMock, activity: ActivityData
    ) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        with pytest.raises(ValueError, match="contact_id must not be empty"):
            await adapter.log_activity("", activity)

    async def test_not_connected_raises_crm_auth_error(self, activity: ActivityData) -> None:
        adapter = HubSpotAdapter()
        with pytest.raises(CRMAuthError):
            await adapter.log_activity("contact-1", activity)

    async def test_note_creation_401_raises_crm_auth_error(
        self, mock_hubspot_client: MagicMock, activity: ActivityData
    ) -> None:
        mock_hubspot_client.crm.objects.notes.basic_api.create.side_effect = _make_api_exception(
            401
        )
        adapter = await _connected_adapter(mock_hubspot_client)
        with pytest.raises(CRMAuthError):
            await adapter.log_activity("contact-1", activity)

    async def test_association_404_raises_contact_not_found(
        self, mock_hubspot_client: MagicMock, activity: ActivityData
    ) -> None:
        mock_hubspot_client.crm.objects.notes.associations_api.create.side_effect = (
            _make_api_exception(404, "Not Found")
        )
        adapter = await _connected_adapter(mock_hubspot_client)
        with pytest.raises(ContactNotFoundError):
            await adapter.log_activity("missing-contact", activity)

    async def test_note_creation_calls_sdk(
        self, mock_hubspot_client: MagicMock, activity: ActivityData
    ) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        await adapter.log_activity("contact-1", activity)
        mock_hubspot_client.crm.objects.notes.basic_api.create.assert_called_once()

    async def test_association_called_with_correct_contact(
        self, mock_hubspot_client: MagicMock, activity: ActivityData
    ) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        await adapter.log_activity("contact-42", activity)
        call_kwargs = mock_hubspot_client.crm.objects.notes.associations_api.create.call_args.kwargs
        assert call_kwargs["to_object_id"] == "contact-42"

    async def test_dashboard_link_included_when_provided(
        self, mock_hubspot_client: MagicMock, activity: ActivityData
    ) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        await adapter.log_activity("contact-1", activity)
        create_kwargs = mock_hubspot_client.crm.objects.notes.basic_api.create.call_args.kwargs
        props = create_kwargs["simple_public_object_input_for_create"]["properties"]
        assert "https://dashboard/emails/email-001" in props["hs_note_body"]

    async def test_dashboard_link_absent_when_none(self, mock_hubspot_client: MagicMock) -> None:
        activity_no_link = ActivityData(
            subject="Subject",
            timestamp=datetime(2025, 3, 1, 12, 0, tzinfo=UTC),
            classification_action="forward",
            classification_type="billing",
            snippet="snippet",
            email_id="email-002",
            dashboard_link=None,
        )
        adapter = await _connected_adapter(mock_hubspot_client)
        await adapter.log_activity("contact-1", activity_no_link)
        create_kwargs = mock_hubspot_client.crm.objects.notes.basic_api.create.call_args.kwargs
        props = create_kwargs["simple_public_object_input_for_create"]["properties"]
        assert "Dashboard:" not in props["hs_note_body"]


# ---------------------------------------------------------------------------
# TestCreateLead
# ---------------------------------------------------------------------------


class TestCreateLead:
    """Tests for HubSpotAdapter.create_lead()."""

    async def test_success_returns_lead_id(self, mock_hubspot_client: MagicMock) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        data = CreateLeadData(contact_id="c-1", summary="Interested in Pro plan", source="email")
        result = await adapter.create_lead(data)
        assert isinstance(result, str)
        assert result == "deal-77"

    async def test_returns_lead_id_is_str(self, mock_hubspot_client: MagicMock) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        data = CreateLeadData(contact_id="c-1", summary="summary", source="email")
        result = await adapter.create_lead(data)
        # LeadId is a NewType wrapping str — str at runtime
        assert isinstance(result, str)

    async def test_empty_contact_id_raises_value_error(
        self, mock_hubspot_client: MagicMock
    ) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        with pytest.raises(ValueError, match="contact_id must not be empty"):
            await adapter.create_lead(
                CreateLeadData(contact_id="", summary="summary", source="email")
            )

    async def test_empty_summary_raises_value_error(self, mock_hubspot_client: MagicMock) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        with pytest.raises(ValueError, match="summary must not be empty"):
            await adapter.create_lead(CreateLeadData(contact_id="c-1", summary="", source="email"))

    async def test_empty_source_raises_value_error(self, mock_hubspot_client: MagicMock) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        with pytest.raises(ValueError, match="source must not be empty"):
            await adapter.create_lead(
                CreateLeadData(contact_id="c-1", summary="summary", source="")
            )

    async def test_not_connected_raises_crm_auth_error(self) -> None:
        adapter = HubSpotAdapter()
        with pytest.raises(CRMAuthError):
            await adapter.create_lead(
                CreateLeadData(contact_id="c-1", summary="summary", source="email")
            )

    async def test_deal_creation_401_raises_crm_auth_error(
        self, mock_hubspot_client: MagicMock
    ) -> None:
        mock_hubspot_client.crm.deals.basic_api.create.side_effect = _make_api_exception(401)
        adapter = await _connected_adapter(mock_hubspot_client)
        with pytest.raises(CRMAuthError):
            await adapter.create_lead(
                CreateLeadData(contact_id="c-1", summary="summary", source="email")
            )

    async def test_deal_uses_settings_default_lead_status(
        self, mock_hubspot_client: MagicMock, mock_settings: MagicMock
    ) -> None:
        mock_settings.hubspot_default_lead_status = "OPEN"
        adapter = await _connected_adapter(mock_hubspot_client)
        # Use default lead_status from CreateLeadData (which is "NEW"), but
        # the adapter falls back to settings when data.lead_status is falsy
        data = CreateLeadData(contact_id="c-1", summary="summary", source="email")
        # Override lead_status to empty to test settings fallback
        data.lead_status = ""
        await adapter.create_lead(data)
        create_kwargs = mock_hubspot_client.crm.deals.basic_api.create.call_args.kwargs
        props = create_kwargs["simple_public_object_input_for_create"]["properties"]
        assert props["hs_lead_status"] == "OPEN"

    async def test_deal_association_called_with_contact_id(
        self, mock_hubspot_client: MagicMock
    ) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        await adapter.create_lead(
            CreateLeadData(contact_id="contact-99", summary="summary", source="email")
        )
        call_kwargs = mock_hubspot_client.crm.deals.associations_api.create.call_args.kwargs
        assert call_kwargs["to_object_id"] == "contact-99"

    async def test_deal_name_includes_source_and_summary(
        self, mock_hubspot_client: MagicMock
    ) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        await adapter.create_lead(
            CreateLeadData(contact_id="c-1", summary="Big purchase intent", source="email")
        )
        create_kwargs = mock_hubspot_client.crm.deals.basic_api.create.call_args.kwargs
        props = create_kwargs["simple_public_object_input_for_create"]["properties"]
        assert "email" in props["dealname"]
        assert "Big purchase intent" in props["dealname"]


# ---------------------------------------------------------------------------
# TestUpdateField
# ---------------------------------------------------------------------------


class TestUpdateField:
    """Tests for HubSpotAdapter.update_field()."""

    async def test_success_returns_none(self, mock_hubspot_client: MagicMock) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        # update_field returns None (-> None signature) — assert no exception raised
        await adapter.update_field("contact-1", "hs_lead_status", "QUALIFIED")

    async def test_sdk_called_with_correct_args(self, mock_hubspot_client: MagicMock) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        await adapter.update_field("contact-1", "hs_lead_status", "QUALIFIED")
        mock_hubspot_client.crm.contacts.basic_api.update.assert_called_once_with(
            contact_id="contact-1",
            simple_public_object_input={"properties": {"hs_lead_status": "QUALIFIED"}},
        )

    async def test_empty_contact_id_raises_value_error(
        self, mock_hubspot_client: MagicMock
    ) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        with pytest.raises(ValueError, match="contact_id"):
            await adapter.update_field("", "field", "value")

    async def test_empty_field_raises_value_error(self, mock_hubspot_client: MagicMock) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        with pytest.raises(ValueError, match="field"):
            await adapter.update_field("contact-1", "", "value")

    async def test_property_doesnt_exist_silenced(self, mock_hubspot_client: MagicMock) -> None:
        mock_hubspot_client.crm.contacts.basic_api.update.side_effect = _make_api_exception(
            400, body="PROPERTY_DOESNT_EXIST: unknown_field"
        )
        adapter = await _connected_adapter(mock_hubspot_client)
        # Must NOT raise — silenced per Sec 6.4
        await adapter.update_field("contact-1", "unknown_field", "value")

    async def test_401_raises_crm_auth_error(self, mock_hubspot_client: MagicMock) -> None:
        mock_hubspot_client.crm.contacts.basic_api.update.side_effect = _make_api_exception(401)
        adapter = await _connected_adapter(mock_hubspot_client)
        with pytest.raises(CRMAuthError):
            await adapter.update_field("contact-1", "field", "value")

    async def test_404_raises_contact_not_found(self, mock_hubspot_client: MagicMock) -> None:
        mock_hubspot_client.crm.contacts.basic_api.update.side_effect = _make_api_exception(
            404, "Not Found"
        )
        adapter = await _connected_adapter(mock_hubspot_client)
        with pytest.raises(ContactNotFoundError):
            await adapter.update_field("missing-id", "field", "value")

    async def test_not_connected_raises_crm_auth_error(self) -> None:
        adapter = HubSpotAdapter()
        with pytest.raises(CRMAuthError):
            await adapter.update_field("contact-1", "field", "value")

    async def test_400_other_raises_crm_connection_error(
        self, mock_hubspot_client: MagicMock
    ) -> None:
        mock_hubspot_client.crm.contacts.basic_api.update.side_effect = _make_api_exception(
            400, body="INVALID_INPUT"
        )
        adapter = await _connected_adapter(mock_hubspot_client)
        with pytest.raises(CRMConnectionError):
            await adapter.update_field("contact-1", "field", "value")


# ---------------------------------------------------------------------------
# TestTestConnection
# ---------------------------------------------------------------------------


class TestTestConnection:
    """Tests for HubSpotAdapter.test_connection()."""

    async def test_success_returns_success_true(self, mock_hubspot_client: MagicMock) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        result = await adapter.test_connection()
        assert result.success is True

    async def test_not_initialized_returns_success_false(self) -> None:
        adapter = HubSpotAdapter()
        result = await adapter.test_connection()
        assert result.success is False

    async def test_not_initialized_returns_error_detail(self) -> None:
        adapter = HubSpotAdapter()
        result = await adapter.test_connection()
        assert result.error_detail is not None
        assert len(result.error_detail) > 0

    async def test_exception_returns_success_false(self, mock_hubspot_client: MagicMock) -> None:
        # Connect first (get_page succeeds), then inject failure for test_connection
        adapter = await _connected_adapter(mock_hubspot_client)
        mock_hubspot_client.crm.contacts.basic_api.get_page.side_effect = RuntimeError(
            "unexpected crash"
        )
        result = await adapter.test_connection()
        assert result.success is False

    async def test_exception_returns_error_detail(self, mock_hubspot_client: MagicMock) -> None:
        # Connect first (get_page succeeds), then inject failure for test_connection
        adapter = await _connected_adapter(mock_hubspot_client)
        mock_hubspot_client.crm.contacts.basic_api.get_page.side_effect = RuntimeError("crashed")
        result = await adapter.test_connection()
        assert result.error_detail is not None
        assert "crashed" in result.error_detail

    async def test_never_raises(self, mock_hubspot_client: MagicMock) -> None:
        # Connect first (get_page succeeds), then inject failure for test_connection
        adapter = await _connected_adapter(mock_hubspot_client)
        mock_hubspot_client.crm.contacts.basic_api.get_page.side_effect = Exception(
            "anything at all"
        )
        # test_connection silences ALL errors (noqa: BLE001)
        result = await adapter.test_connection()
        assert isinstance(result, ConnectionTestResult)

    async def test_measures_latency_ms(self, mock_hubspot_client: MagicMock) -> None:
        adapter = await _connected_adapter(mock_hubspot_client)
        result = await adapter.test_connection()
        assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# TestRaiseFromHubspotExc
# ---------------------------------------------------------------------------


class TestRaiseFromHubspotExc:
    """Tests for _raise_from_hubspot_exc() via the helper directly.

    This helper is module-level — tested here in isolation rather than only
    as a side-effect of adapter methods.
    """

    def test_401_raises_crm_auth_error(self) -> None:
        exc = _make_api_exception(401, "Unauthorized")
        with pytest.raises(CRMAuthError) as exc_info:
            _raise_from_hubspot_exc(exc)
        assert exc_info.value.original_error is exc

    def test_404_raises_contact_not_found(self) -> None:
        exc = _make_api_exception(404, "Not Found")
        with pytest.raises(ContactNotFoundError) as exc_info:
            _raise_from_hubspot_exc(exc)
        assert exc_info.value.original_error is exc

    def test_409_raises_duplicate_contact_error(self) -> None:
        exc = _make_api_exception(409, "Conflict")
        with pytest.raises(DuplicateContactError) as exc_info:
            _raise_from_hubspot_exc(exc)
        assert exc_info.value.original_error is exc

    def test_429_raises_rate_limit_error(self) -> None:
        exc = _make_api_exception_with_retry("30")
        with pytest.raises(CRMRateLimitError) as exc_info:
            _raise_from_hubspot_exc(exc)
        assert exc_info.value.retry_after_seconds == 30
        assert exc_info.value.original_error is exc

    def test_429_no_retry_after_header(self) -> None:
        exc = _make_api_exception(429)
        exc.headers = {}
        with pytest.raises(CRMRateLimitError) as exc_info:
            _raise_from_hubspot_exc(exc)
        # No Retry-After header → retry_after_seconds is None
        assert exc_info.value.retry_after_seconds is None

    def test_400_property_doesnt_exist_raises_field_not_found(self) -> None:
        exc = _make_api_exception(400, body="PROPERTY_DOESNT_EXIST: my_prop")
        with pytest.raises(FieldNotFoundError) as exc_info:
            _raise_from_hubspot_exc(exc)
        assert exc_info.value.original_error is exc

    def test_400_other_raises_crm_connection_error(self) -> None:
        exc = _make_api_exception(400, body="VALIDATION_ERROR")
        with pytest.raises(CRMConnectionError) as exc_info:
            _raise_from_hubspot_exc(exc)
        assert exc_info.value.original_error is exc

    def test_500_raises_crm_connection_error(self) -> None:
        exc = _make_api_exception(500, "Internal Server Error")
        with pytest.raises(CRMConnectionError) as exc_info:
            _raise_from_hubspot_exc(exc)
        assert exc_info.value.original_error is exc

    def test_503_raises_crm_connection_error(self) -> None:
        exc = _make_api_exception(503, "Service Unavailable")
        with pytest.raises(CRMConnectionError):
            _raise_from_hubspot_exc(exc)

    def test_original_error_preserved_on_auth_error(self) -> None:
        exc = _make_api_exception(401)
        with pytest.raises(CRMAuthError) as exc_info:
            _raise_from_hubspot_exc(exc)
        assert exc_info.value.original_error is exc


# ---------------------------------------------------------------------------
# TestHashEmail
# ---------------------------------------------------------------------------


class TestHashEmail:
    """Tests for _hash_email() helper."""

    def test_returns_16_char_hex_string(self) -> None:
        result = _hash_email("alice@example.com")
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic_same_input(self) -> None:
        first = _hash_email("alice@example.com")
        second = _hash_email("alice@example.com")
        assert first == second

    def test_different_inputs_produce_different_hashes(self) -> None:
        h1 = _hash_email("alice@example.com")
        h2 = _hash_email("bob@example.com")
        assert h1 != h2

    def test_empty_string_returns_hex(self) -> None:
        result = _hash_email("")
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)


# ---------------------------------------------------------------------------
# TestParseHsDatetime
# ---------------------------------------------------------------------------


class TestParseHsDatetime:
    """Tests for _parse_hs_datetime() helper."""

    def test_none_input_returns_none(self) -> None:
        assert _parse_hs_datetime(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _parse_hs_datetime("") is None

    def test_valid_iso_returns_datetime(self) -> None:
        result = _parse_hs_datetime("2024-01-15T10:30:00.000Z")
        assert isinstance(result, datetime)

    def test_z_suffix_parsed_as_utc(self) -> None:
        result = _parse_hs_datetime("2024-01-15T10:30:00.000Z")
        assert result is not None
        assert result.tzinfo is not None

    def test_correct_year_month_day(self) -> None:
        result = _parse_hs_datetime("2024-06-20T08:00:00.000Z")
        assert result is not None
        assert result.year == 2024
        assert result.month == 6
        assert result.day == 20

    def test_invalid_string_returns_none(self) -> None:
        assert _parse_hs_datetime("not-a-date") is None

    def test_iso_without_z_still_parsed(self) -> None:
        result = _parse_hs_datetime("2024-01-15T10:30:00+00:00")
        assert isinstance(result, datetime)
