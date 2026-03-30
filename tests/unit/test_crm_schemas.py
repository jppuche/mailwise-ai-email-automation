"""Unit tests for CRM adapter boundary schemas.

Validates Pydantic models and NewTypes for ActivityId, LeadId,
CRMCredentials, ConnectionStatus, ConnectionTestResult, Contact,
CreateContactData, ActivityData, and CreateLeadData.
No external dependencies — pure schema validation.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

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
# ActivityId / LeadId (NewType)
# ---------------------------------------------------------------------------


class TestActivityId:
    """Validates ActivityId NewType behaves as str."""

    def test_creates_from_str(self) -> None:
        aid = ActivityId("note-123")
        assert aid == "note-123"

    def test_is_str_instance(self) -> None:
        aid = ActivityId("hs-activity-456")
        assert isinstance(aid, str)

    def test_equality_with_plain_str(self) -> None:
        aid = ActivityId("note-abc")
        assert aid == "note-abc"

    def test_empty_string_accepted(self) -> None:
        # NewType is a callable alias — no runtime validation
        aid = ActivityId("")
        assert aid == ""


class TestLeadId:
    """Validates LeadId NewType behaves as str."""

    def test_creates_from_str(self) -> None:
        lid = LeadId("deal-789")
        assert lid == "deal-789"

    def test_is_str_instance(self) -> None:
        lid = LeadId("hs-deal-001")
        assert isinstance(lid, str)

    def test_equality_with_plain_str(self) -> None:
        lid = LeadId("lead-xyz")
        assert lid == "lead-xyz"

    def test_distinct_from_activity_id(self) -> None:
        """NewTypes are callable aliases; values compare equal when same string."""
        aid = ActivityId("shared-id")
        lid = LeadId("shared-id")
        assert aid == lid  # same underlying str value


# ---------------------------------------------------------------------------
# CRMCredentials
# ---------------------------------------------------------------------------


class TestCRMCredentials:
    """Validates CRMCredentials access_token field requirements."""

    def test_valid_construction(self) -> None:
        creds = CRMCredentials(access_token="pat-na1-abc123")
        assert creds.access_token == "pat-na1-abc123"

    def test_empty_string_accepted(self) -> None:
        # Validation (non-empty) is adapter responsibility, not schema
        creds = CRMCredentials(access_token="")
        assert creds.access_token == ""

    def test_missing_access_token_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CRMCredentials()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ConnectionStatus
# ---------------------------------------------------------------------------


class TestConnectionStatus:
    """Validates ConnectionStatus optional fields default to None."""

    def test_connected_with_all_fields(self) -> None:
        status = ConnectionStatus(
            connected=True,
            portal_id="12345678",
            account_name="Mailwise Corp",
            error=None,
        )
        assert status.connected is True
        assert status.portal_id == "12345678"
        assert status.account_name == "Mailwise Corp"
        assert status.error is None

    def test_disconnected_with_error(self) -> None:
        status = ConnectionStatus(connected=False, error="UNAUTHORIZED")
        assert status.connected is False
        assert status.error == "UNAUTHORIZED"
        assert status.portal_id is None
        assert status.account_name is None

    def test_connected_minimal(self) -> None:
        status = ConnectionStatus(connected=True)
        assert status.connected is True
        assert status.portal_id is None
        assert status.account_name is None
        assert status.error is None

    def test_missing_connected_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ConnectionStatus()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ConnectionTestResult
# ---------------------------------------------------------------------------


class TestConnectionTestResult:
    """Validates ConnectionTestResult; latency_ms is required."""

    def test_success_result(self) -> None:
        result = ConnectionTestResult(
            success=True,
            portal_id="12345678",
            latency_ms=42,
        )
        assert result.success is True
        assert result.portal_id == "12345678"
        assert result.latency_ms == 42
        assert result.error_detail is None

    def test_failure_result_with_error_detail(self) -> None:
        result = ConnectionTestResult(
            success=False,
            latency_ms=0,
            error_detail="authentication_failed",
        )
        assert result.success is False
        assert result.error_detail == "authentication_failed"
        assert result.portal_id is None

    def test_latency_ms_required(self) -> None:
        """latency_ms has no default — must be supplied."""
        with pytest.raises(ValidationError):
            ConnectionTestResult(success=True)  # type: ignore[call-arg]

    def test_optional_fields_default_to_none(self) -> None:
        result = ConnectionTestResult(success=True, latency_ms=10)
        assert result.portal_id is None
        assert result.error_detail is None

    def test_missing_success_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ConnectionTestResult(latency_ms=10)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Contact
# ---------------------------------------------------------------------------


class TestContact:
    """Validates Contact construction and optional field defaults."""

    def test_minimal_fields(self) -> None:
        contact = Contact(id="1001", email="alice@example.com")
        assert contact.id == "1001"
        assert contact.email == "alice@example.com"
        assert contact.first_name is None
        assert contact.last_name is None
        assert contact.company is None
        assert contact.created_at is None
        assert contact.updated_at is None

    def test_full_fields(self) -> None:
        now = datetime.now(tz=UTC)
        contact = Contact(
            id="1002",
            email="bob@corp.com",
            first_name="Bob",
            last_name="Smith",
            company="Corp Inc",
            created_at=now,
            updated_at=now,
        )
        assert contact.first_name == "Bob"
        assert contact.last_name == "Smith"
        assert contact.company == "Corp Inc"
        assert contact.created_at == now
        assert contact.updated_at == now

    def test_numeric_id_as_str(self) -> None:
        contact = Contact(id="99999999", email="user@example.com")
        assert contact.id == "99999999"
        assert isinstance(contact.id, str)

    def test_missing_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Contact(email="a@b.com")  # type: ignore[call-arg]

    def test_missing_email_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Contact(id="1")  # type: ignore[call-arg]

    def test_created_at_without_updated_at(self) -> None:
        now = datetime.now(tz=UTC)
        contact = Contact(id="1003", email="c@d.com", created_at=now)
        assert contact.created_at == now
        assert contact.updated_at is None


# ---------------------------------------------------------------------------
# CreateContactData
# ---------------------------------------------------------------------------


class TestCreateContactData:
    """Validates CreateContactData email validator and optional fields."""

    def test_valid_email(self) -> None:
        data = CreateContactData(email="newuser@company.com")
        assert data.email == "newuser@company.com"
        assert data.first_name is None
        assert data.last_name is None
        assert data.company is None
        assert data.source is None
        assert data.first_interaction_at is None

    def test_full_fields(self) -> None:
        now = datetime.now(tz=UTC)
        data = CreateContactData(
            email="lead@startup.io",
            first_name="Jane",
            last_name="Doe",
            company="Startup IO",
            source="inbound_email",
            first_interaction_at=now,
        )
        assert data.first_name == "Jane"
        assert data.last_name == "Doe"
        assert data.company == "Startup IO"
        assert data.source == "inbound_email"
        assert data.first_interaction_at == now

    def test_invalid_email_no_at_rejected(self) -> None:
        with pytest.raises(ValidationError, match="@"):
            CreateContactData(email="notanemail")

    def test_invalid_email_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateContactData(email="")

    def test_missing_email_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateContactData()  # type: ignore[call-arg]

    def test_email_with_subdomain_valid(self) -> None:
        data = CreateContactData(email="contact@mail.corp.example.com")
        assert data.email == "contact@mail.corp.example.com"

    def test_email_at_symbol_only_prefix_accepted(self) -> None:
        """Validator only checks for '@' presence — minimal contract."""
        data = CreateContactData(email="@domain.com")
        assert "@" in data.email


# ---------------------------------------------------------------------------
# ActivityData
# ---------------------------------------------------------------------------


class TestActivityData:
    """Validates ActivityData required fields and optional dashboard_link."""

    def _make_activity(self, **overrides: object) -> ActivityData:
        defaults: dict[str, object] = {
            "subject": "Re: Support ticket #42",
            "timestamp": datetime(2026, 2, 21, 10, 0, tzinfo=UTC),
            "classification_action": "reply",
            "classification_type": "support",
            "snippet": "Customer asked about billing...",
            "email_id": "email-abc123",
        }
        defaults.update(overrides)
        return ActivityData(**defaults)  # type: ignore[arg-type]

    def test_minimal_construction(self) -> None:
        activity = self._make_activity()
        assert activity.subject == "Re: Support ticket #42"
        assert activity.classification_action == "reply"
        assert activity.classification_type == "support"
        assert activity.snippet == "Customer asked about billing..."
        assert activity.email_id == "email-abc123"
        assert activity.dashboard_link is None

    def test_with_dashboard_link(self) -> None:
        activity = self._make_activity(dashboard_link="https://app.mailwise.io/emails/email-abc123")
        assert activity.dashboard_link == "https://app.mailwise.io/emails/email-abc123"

    def test_timezone_aware_timestamp_preserved(self) -> None:
        ts = datetime(2026, 2, 28, 15, 30, 0, tzinfo=UTC)
        activity = self._make_activity(timestamp=ts)
        assert activity.timestamp == ts

    def test_missing_subject_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ActivityData(
                timestamp=datetime(2026, 2, 21, 10, 0, tzinfo=UTC),
                classification_action="reply",
                classification_type="support",
                snippet="...",
                email_id="email-1",
            )  # type: ignore[call-arg]

    def test_missing_email_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ActivityData(
                subject="Hello",
                timestamp=datetime(2026, 2, 21, 10, 0, tzinfo=UTC),
                classification_action="reply",
                classification_type="support",
                snippet="...",
            )  # type: ignore[call-arg]

    def test_missing_snippet_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ActivityData(
                subject="Hello",
                timestamp=datetime(2026, 2, 21, 10, 0, tzinfo=UTC),
                classification_action="reply",
                classification_type="support",
                email_id="email-1",
            )  # type: ignore[call-arg]

    def test_missing_classification_action_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ActivityData(
                subject="Hello",
                timestamp=datetime(2026, 2, 21, 10, 0, tzinfo=UTC),
                classification_type="support",
                snippet="...",
                email_id="email-1",
            )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# CreateLeadData
# ---------------------------------------------------------------------------


class TestCreateLeadData:
    """Validates CreateLeadData required fields and lead_status default."""

    def test_minimal_construction(self) -> None:
        data = CreateLeadData(
            contact_id="1001",
            summary="High-value prospect inquiry",
            source="inbound_email",
        )
        assert data.contact_id == "1001"
        assert data.summary == "High-value prospect inquiry"
        assert data.source == "inbound_email"
        assert data.lead_status == "NEW"

    def test_lead_status_default_is_new(self) -> None:
        data = CreateLeadData(
            contact_id="2001",
            summary="Demo request",
            source="website",
        )
        assert data.lead_status == "NEW"

    def test_custom_lead_status(self) -> None:
        data = CreateLeadData(
            contact_id="3001",
            summary="Follow-up needed",
            source="referral",
            lead_status="IN_PROGRESS",
        )
        assert data.lead_status == "IN_PROGRESS"

    def test_missing_contact_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateLeadData(
                summary="Some summary",
                source="inbound_email",
            )  # type: ignore[call-arg]

    def test_missing_summary_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateLeadData(
                contact_id="1001",
                source="inbound_email",
            )  # type: ignore[call-arg]

    def test_missing_source_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateLeadData(
                contact_id="1001",
                summary="Some summary",
            )  # type: ignore[call-arg]
