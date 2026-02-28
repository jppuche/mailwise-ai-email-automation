"""Contract tests for the CRMAdapter ABC.

Uses a ``MockCRMAdapter`` that implements all 7 abstract methods.
Verifies that *any* correct implementation satisfies the contract:
correct return types, expected exceptions for invalid inputs,
``test_connection()`` never raises, exception hierarchy, ABC enforcement.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.adapters.crm.base import CRMAdapter
from src.adapters.crm.exceptions import (
    ContactNotFoundError,
    CRMAdapterError,
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

# ---------------------------------------------------------------------------
# MockCRMAdapter — minimal concrete implementation
# ---------------------------------------------------------------------------


class MockCRMAdapter(CRMAdapter):
    """Simplest valid implementation satisfying the ABC contract."""

    def __init__(self) -> None:
        self._connected = False

    async def connect(self, credentials: CRMCredentials) -> ConnectionStatus:
        if not credentials.access_token:
            raise ValueError("access_token must not be empty")
        self._connected = True
        return ConnectionStatus(connected=True, portal_id="test-portal")

    async def lookup_contact(self, email: str) -> Contact | None:
        if not email or "@" not in email:
            raise ValueError(f"Invalid email: {email!r}")
        if not self._connected:
            raise CRMAuthError("Not connected")
        return Contact(id="1", email=email, first_name="Test")

    async def create_contact(self, data: CreateContactData) -> Contact:
        if not self._connected:
            raise CRMAuthError("Not connected")
        return Contact(id="2", email=data.email, first_name=data.first_name)

    async def log_activity(self, contact_id: str, activity: ActivityData) -> ActivityId:
        if not contact_id:
            raise ValueError("contact_id must not be empty")
        if not self._connected:
            raise CRMAuthError("Not connected")
        return ActivityId("note-1")

    async def create_lead(self, data: CreateLeadData) -> LeadId:
        if not data.contact_id:
            raise ValueError("contact_id must not be empty")
        if not data.summary:
            raise ValueError("summary must not be empty")
        if not data.source:
            raise ValueError("source must not be empty")
        if not self._connected:
            raise CRMAuthError("Not connected")
        return LeadId("deal-1")

    async def update_field(self, contact_id: str, field: str, value: str) -> None:
        if not contact_id:
            raise ValueError("contact_id must not be empty")
        if not field:
            raise ValueError("field must not be empty")
        if not self._connected:
            raise CRMAuthError("Not connected")

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(success=self._connected, latency_ms=1)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def adapter() -> MockCRMAdapter:
    return MockCRMAdapter()


@pytest.fixture
def connected_adapter() -> MockCRMAdapter:
    """Adapter that has already been connected."""
    a = MockCRMAdapter()
    a._connected = True
    return a


@pytest.fixture
def credentials() -> CRMCredentials:
    return CRMCredentials(access_token="test-private-app-token")


@pytest.fixture
def activity() -> ActivityData:
    return ActivityData(
        subject="Re: Support Request",
        timestamp=datetime(2025, 1, 20, 10, 0, tzinfo=UTC),
        classification_action="reply",
        classification_type="support",
        snippet="Please help with my account.",
        email_id="email-001",
        dashboard_link="https://dashboard/emails/email-001",
    )


# ---------------------------------------------------------------------------
# ABC satisfiability
# ---------------------------------------------------------------------------


class TestABCSatisfiability:
    """MockCRMAdapter must be instantiable and recognised as CRMAdapter."""

    def test_can_instantiate_mock(self) -> None:
        mock = MockCRMAdapter()
        assert mock is not None

    def test_is_instance_of_crm_adapter(self) -> None:
        mock = MockCRMAdapter()
        assert isinstance(mock, CRMAdapter)

    def test_has_all_seven_abstract_methods(self) -> None:
        expected = {
            "connect",
            "lookup_contact",
            "create_contact",
            "log_activity",
            "create_lead",
            "update_field",
            "test_connection",
        }
        assert expected.issubset(set(dir(MockCRMAdapter)))


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """All CRM exceptions must inherit from CRMAdapterError."""

    def test_crm_auth_error_is_crm_adapter_error(self) -> None:
        exc = CRMAuthError("auth failed")
        assert isinstance(exc, CRMAdapterError)

    def test_crm_rate_limit_error_is_crm_adapter_error(self) -> None:
        exc = CRMRateLimitError("rate limited", retry_after_seconds=30)
        assert isinstance(exc, CRMAdapterError)

    def test_crm_rate_limit_error_has_retry_after_seconds(self) -> None:
        exc = CRMRateLimitError("rate limited", retry_after_seconds=30)
        assert exc.retry_after_seconds == 30

    def test_crm_rate_limit_error_retry_after_seconds_can_be_none(self) -> None:
        exc = CRMRateLimitError("rate limited")
        assert exc.retry_after_seconds is None

    def test_crm_connection_error_is_crm_adapter_error(self) -> None:
        exc = CRMConnectionError("network error")
        assert isinstance(exc, CRMAdapterError)

    def test_duplicate_contact_error_is_crm_adapter_error(self) -> None:
        exc = DuplicateContactError("duplicate")
        assert isinstance(exc, CRMAdapterError)

    def test_contact_not_found_error_is_crm_adapter_error(self) -> None:
        exc = ContactNotFoundError("not found")
        assert isinstance(exc, CRMAdapterError)

    def test_field_not_found_error_is_crm_adapter_error(self) -> None:
        exc = FieldNotFoundError("field missing")
        assert isinstance(exc, CRMAdapterError)

    def test_crm_adapter_error_has_original_error_attribute(self) -> None:
        original = ValueError("underlying cause")
        exc = CRMAdapterError("wrapped", original_error=original)
        assert exc.original_error is original

    def test_crm_adapter_error_original_error_defaults_to_none(self) -> None:
        exc = CRMAdapterError("no cause")
        assert exc.original_error is None


# ---------------------------------------------------------------------------
# connect() contract
# ---------------------------------------------------------------------------


class TestConnectContract:
    """Any CRMAdapter.connect() implementation must satisfy these."""

    async def test_returns_connection_status(
        self,
        adapter: MockCRMAdapter,
        credentials: CRMCredentials,
    ) -> None:
        result = await adapter.connect(credentials)
        assert isinstance(result, ConnectionStatus)

    async def test_connected_is_true_on_success(
        self,
        adapter: MockCRMAdapter,
        credentials: CRMCredentials,
    ) -> None:
        result = await adapter.connect(credentials)
        assert result.connected is True

    async def test_empty_access_token_raises_value_error(
        self,
        adapter: MockCRMAdapter,
    ) -> None:
        with pytest.raises(ValueError, match="access_token"):
            await adapter.connect(CRMCredentials(access_token=""))


# ---------------------------------------------------------------------------
# lookup_contact() contract
# ---------------------------------------------------------------------------


class TestLookupContactContract:
    """Any CRMAdapter.lookup_contact() implementation must satisfy these."""

    async def test_returns_contact_when_connected(
        self,
        connected_adapter: MockCRMAdapter,
    ) -> None:
        result = await connected_adapter.lookup_contact("alice@example.com")
        assert isinstance(result, Contact)

    async def test_returns_contact_or_none(
        self,
        connected_adapter: MockCRMAdapter,
    ) -> None:
        result = await connected_adapter.lookup_contact("alice@example.com")
        assert result is None or isinstance(result, Contact)

    async def test_empty_email_raises_value_error(
        self,
        connected_adapter: MockCRMAdapter,
    ) -> None:
        with pytest.raises(ValueError):
            await connected_adapter.lookup_contact("")

    async def test_email_without_at_raises_value_error(
        self,
        connected_adapter: MockCRMAdapter,
    ) -> None:
        with pytest.raises(ValueError):
            await connected_adapter.lookup_contact("not-an-email")

    async def test_not_connected_raises_crm_auth_error(
        self,
        adapter: MockCRMAdapter,
    ) -> None:
        with pytest.raises(CRMAuthError):
            await adapter.lookup_contact("alice@example.com")


# ---------------------------------------------------------------------------
# create_contact() contract
# ---------------------------------------------------------------------------


class TestCreateContactContract:
    """Any CRMAdapter.create_contact() implementation must satisfy these."""

    async def test_returns_contact_when_connected(
        self,
        connected_adapter: MockCRMAdapter,
    ) -> None:
        data = CreateContactData(email="bob@example.com", first_name="Bob")
        result = await connected_adapter.create_contact(data)
        assert isinstance(result, Contact)

    async def test_returned_contact_has_id(
        self,
        connected_adapter: MockCRMAdapter,
    ) -> None:
        data = CreateContactData(email="bob@example.com")
        result = await connected_adapter.create_contact(data)
        assert isinstance(result.id, str)
        assert result.id != ""

    async def test_not_connected_raises_crm_auth_error(
        self,
        adapter: MockCRMAdapter,
    ) -> None:
        data = CreateContactData(email="bob@example.com")
        with pytest.raises(CRMAuthError):
            await adapter.create_contact(data)


# ---------------------------------------------------------------------------
# log_activity() contract
# ---------------------------------------------------------------------------


class TestLogActivityContract:
    """Any CRMAdapter.log_activity() implementation must satisfy these."""

    async def test_returns_activity_id_when_connected(
        self,
        connected_adapter: MockCRMAdapter,
        activity: ActivityData,
    ) -> None:
        result = await connected_adapter.log_activity("contact-1", activity)
        assert isinstance(result, str)

    async def test_empty_contact_id_raises_value_error(
        self,
        connected_adapter: MockCRMAdapter,
        activity: ActivityData,
    ) -> None:
        with pytest.raises(ValueError, match="contact_id"):
            await connected_adapter.log_activity("", activity)

    async def test_not_connected_raises_crm_auth_error(
        self,
        adapter: MockCRMAdapter,
        activity: ActivityData,
    ) -> None:
        with pytest.raises(CRMAuthError):
            await adapter.log_activity("contact-1", activity)


# ---------------------------------------------------------------------------
# create_lead() contract
# ---------------------------------------------------------------------------


class TestCreateLeadContract:
    """Any CRMAdapter.create_lead() implementation must satisfy these."""

    async def test_returns_lead_id_when_connected(
        self,
        connected_adapter: MockCRMAdapter,
    ) -> None:
        data = CreateLeadData(
            contact_id="contact-1",
            summary="High-value lead from support",
            source="email",
        )
        result = await connected_adapter.create_lead(data)
        assert isinstance(result, str)

    async def test_empty_contact_id_raises_value_error(
        self,
        connected_adapter: MockCRMAdapter,
    ) -> None:
        data = CreateLeadData(contact_id="", summary="summary", source="email")
        with pytest.raises(ValueError, match="contact_id"):
            await connected_adapter.create_lead(data)

    async def test_empty_summary_raises_value_error(
        self,
        connected_adapter: MockCRMAdapter,
    ) -> None:
        data = CreateLeadData(contact_id="c-1", summary="", source="email")
        with pytest.raises(ValueError, match="summary"):
            await connected_adapter.create_lead(data)

    async def test_empty_source_raises_value_error(
        self,
        connected_adapter: MockCRMAdapter,
    ) -> None:
        data = CreateLeadData(contact_id="c-1", summary="summary", source="")
        with pytest.raises(ValueError, match="source"):
            await connected_adapter.create_lead(data)

    async def test_not_connected_raises_crm_auth_error(
        self,
        adapter: MockCRMAdapter,
    ) -> None:
        data = CreateLeadData(contact_id="c-1", summary="summary", source="email")
        with pytest.raises(CRMAuthError):
            await adapter.create_lead(data)


# ---------------------------------------------------------------------------
# update_field() contract
# ---------------------------------------------------------------------------


class TestUpdateFieldContract:
    """Any CRMAdapter.update_field() implementation must satisfy these."""

    async def test_returns_none_when_connected(
        self,
        connected_adapter: MockCRMAdapter,
    ) -> None:
        # update_field returns None — must complete without raising
        await connected_adapter.update_field("contact-1", "hs_lead_status", "NEW")

    async def test_empty_contact_id_raises_value_error(
        self,
        connected_adapter: MockCRMAdapter,
    ) -> None:
        with pytest.raises(ValueError, match="contact_id"):
            await connected_adapter.update_field("", "field", "value")

    async def test_empty_field_raises_value_error(
        self,
        connected_adapter: MockCRMAdapter,
    ) -> None:
        with pytest.raises(ValueError, match="field"):
            await connected_adapter.update_field("contact-1", "", "value")

    async def test_not_connected_raises_crm_auth_error(
        self,
        adapter: MockCRMAdapter,
    ) -> None:
        with pytest.raises(CRMAuthError):
            await adapter.update_field("contact-1", "field", "value")


# ---------------------------------------------------------------------------
# test_connection() contract
# ---------------------------------------------------------------------------


class TestTestConnectionContract:
    """test_connection() must NEVER raise — always returns ConnectionTestResult."""

    async def test_returns_connection_test_result(
        self,
        adapter: MockCRMAdapter,
    ) -> None:
        result = await adapter.test_connection()
        assert isinstance(result, ConnectionTestResult)

    async def test_never_raises_on_unconnected_adapter(
        self,
        adapter: MockCRMAdapter,
    ) -> None:
        # Must complete without exception on a fresh (unconnected) adapter.
        result = await adapter.test_connection()
        assert result is not None

    async def test_has_latency_ms(
        self,
        adapter: MockCRMAdapter,
    ) -> None:
        result = await adapter.test_connection()
        assert result.latency_ms >= 0

    async def test_success_reflects_connection_state(
        self,
        connected_adapter: MockCRMAdapter,
    ) -> None:
        result = await connected_adapter.test_connection()
        assert result.success is True


# ---------------------------------------------------------------------------
# ABC enforcement
# ---------------------------------------------------------------------------


class TestABCEnforcement:
    """Cannot instantiate CRMAdapter without implementing all methods."""

    def test_cannot_instantiate_abc_directly(self) -> None:
        with pytest.raises(TypeError, match="abstract method"):
            CRMAdapter()  # type: ignore[abstract]

    def test_partial_implementation_raises(self) -> None:
        class PartialAdapter(CRMAdapter):
            async def connect(self, credentials: CRMCredentials) -> ConnectionStatus:
                return ConnectionStatus(connected=True)

        with pytest.raises(TypeError, match="abstract method"):
            PartialAdapter()  # type: ignore[abstract]
