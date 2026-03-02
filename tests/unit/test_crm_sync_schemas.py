"""Tests for CRM sync service schemas."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.services.schemas.crm_sync import (
    CRMOperationStatus,
    CRMSyncConfig,
    CRMSyncRequest,
    CRMSyncResult,
)

# ---------------------------------------------------------------------------
# CRMSyncConfig
# ---------------------------------------------------------------------------


class TestCRMSyncConfig:
    def test_crm_sync_config_all_fields_valid(self) -> None:
        config = CRMSyncConfig(
            auto_create_contacts=True,
            activity_snippet_length=200,
            retry_max=3,
            backoff_base_seconds=60,
        )
        assert config.auto_create_contacts is True
        assert config.activity_snippet_length == 200
        assert config.retry_max == 3
        assert config.backoff_base_seconds == 60

    def test_crm_sync_config_missing_auto_create_contacts_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            CRMSyncConfig(  # type: ignore[call-arg]
                activity_snippet_length=200,
                retry_max=3,
                backoff_base_seconds=60,
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("auto_create_contacts",) for e in errors)

    def test_crm_sync_config_missing_retry_max_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            CRMSyncConfig(  # type: ignore[call-arg]
                auto_create_contacts=False,
                activity_snippet_length=200,
                backoff_base_seconds=60,
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("retry_max",) for e in errors)

    def test_crm_sync_config_missing_backoff_base_seconds_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            CRMSyncConfig(  # type: ignore[call-arg]
                auto_create_contacts=False,
                activity_snippet_length=200,
                retry_max=3,
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("backoff_base_seconds",) for e in errors)


# ---------------------------------------------------------------------------
# CRMSyncRequest
# ---------------------------------------------------------------------------


class TestCRMSyncRequest:
    def _valid_payload(self, **overrides: object) -> dict[str, object]:
        defaults: dict[str, object] = {
            "email_id": uuid.uuid4(),
            "sender_email": "customer@example.com",
            "subject": "Invoice issue",
            "snippet": "I have not received my invoice.",
            "classification_action": "reply",
            "classification_type": "complaint",
            "received_at": datetime.now(UTC),
        }
        defaults.update(overrides)
        return defaults

    def test_crm_sync_request_happy_path_all_fields(self) -> None:
        email_id = uuid.uuid4()
        received_at = datetime.now(UTC)
        req = CRMSyncRequest(
            email_id=email_id,
            sender_email="customer@example.com",
            sender_name="Alice Smith",
            subject="Invoice issue",
            snippet="I have not received my invoice.",
            classification_action="reply",
            classification_type="complaint",
            received_at=received_at,
            create_lead=True,
            field_updates={"status": "vip"},
        )
        assert req.email_id == email_id
        assert req.sender_email == "customer@example.com"
        assert req.sender_name == "Alice Smith"
        assert req.subject == "Invoice issue"
        assert req.snippet == "I have not received my invoice."
        assert req.classification_action == "reply"
        assert req.classification_type == "complaint"
        assert req.received_at == received_at
        assert req.create_lead is True
        assert req.field_updates == {"status": "vip"}

    def test_crm_sync_request_sender_name_optional_none_by_default(self) -> None:
        req = CRMSyncRequest(**self._valid_payload())  # type: ignore[arg-type]
        assert req.sender_name is None

    def test_crm_sync_request_create_lead_default_false(self) -> None:
        req = CRMSyncRequest(**self._valid_payload())  # type: ignore[arg-type]
        assert req.create_lead is False

    def test_crm_sync_request_field_updates_default_empty_dict(self) -> None:
        req = CRMSyncRequest(**self._valid_payload())  # type: ignore[arg-type]
        assert req.field_updates == {}

    def test_crm_sync_request_missing_required_field_raises(self) -> None:
        payload = self._valid_payload()
        del payload["sender_email"]
        with pytest.raises(ValidationError) as exc_info:
            CRMSyncRequest(**payload)  # type: ignore[arg-type]
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("sender_email",) for e in errors)

    def test_crm_sync_request_email_id_from_string_uuid(self) -> None:
        raw_id = uuid.uuid4()
        req = CRMSyncRequest(**self._valid_payload(email_id=str(raw_id)))  # type: ignore[arg-type]
        assert isinstance(req.email_id, uuid.UUID)
        assert req.email_id == raw_id

    def test_crm_sync_request_field_updates_str_str_type(self) -> None:
        req = CRMSyncRequest(
            **self._valid_payload(field_updates={"lifecycle_stage": "customer", "priority": "high"})  # type: ignore[arg-type]
        )
        for k, v in req.field_updates.items():
            assert isinstance(k, str)
            assert isinstance(v, str)


# ---------------------------------------------------------------------------
# Privacy — body fields must not exist
# ---------------------------------------------------------------------------


class TestCRMSyncRequestPrivacy:
    def test_body_plain_not_in_model_fields(self) -> None:
        assert "body_plain" not in CRMSyncRequest.model_fields

    def test_body_html_not_in_model_fields(self) -> None:
        assert "body_html" not in CRMSyncRequest.model_fields


# ---------------------------------------------------------------------------
# CRMOperationStatus
# ---------------------------------------------------------------------------


class TestCRMOperationStatus:
    def test_operation_contact_lookup_valid(self) -> None:
        op = CRMOperationStatus(operation="contact_lookup", success=True)
        assert op.operation == "contact_lookup"
        assert op.success is True

    def test_operation_contact_create_valid(self) -> None:
        op = CRMOperationStatus(operation="contact_create", success=True, crm_id="123")
        assert op.operation == "contact_create"
        assert op.crm_id == "123"

    def test_operation_activity_log_valid(self) -> None:
        op = CRMOperationStatus(operation="activity_log", success=True, crm_id="act-456")
        assert op.operation == "activity_log"

    def test_operation_lead_create_valid(self) -> None:
        op = CRMOperationStatus(operation="lead_create", success=True, crm_id="lead-789")
        assert op.operation == "lead_create"

    def test_operation_field_update_valid(self) -> None:
        op = CRMOperationStatus(operation="field_update", success=True)
        assert op.operation == "field_update"

    def test_operation_invalid_literal_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            CRMOperationStatus(operation="unknown_op", success=True)  # type: ignore[arg-type]
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("operation",) for e in errors)

    def test_crm_id_defaults_none(self) -> None:
        op = CRMOperationStatus(operation="contact_lookup", success=False)
        assert op.crm_id is None

    def test_skipped_defaults_false(self) -> None:
        op = CRMOperationStatus(operation="contact_lookup", success=True)
        assert op.skipped is False

    def test_error_defaults_none(self) -> None:
        op = CRMOperationStatus(operation="contact_lookup", success=True)
        assert op.error is None

    def test_failed_operation_with_error_message(self) -> None:
        op = CRMOperationStatus(
            operation="contact_create",
            success=False,
            error="Rate limit exceeded",
        )
        assert op.success is False
        assert op.error == "Rate limit exceeded"
        assert op.crm_id is None


# ---------------------------------------------------------------------------
# CRMSyncResult
# ---------------------------------------------------------------------------


class TestCRMSyncResult:
    def _make_operation(
        self,
        operation: str = "contact_lookup",
        success: bool = True,
    ) -> CRMOperationStatus:
        return CRMOperationStatus(operation=operation, success=success)  # type: ignore[arg-type]

    def test_crm_sync_result_happy_path(self) -> None:
        email_id = uuid.uuid4()
        ops = [
            self._make_operation("contact_lookup", True),
            self._make_operation("activity_log", True),
        ]
        result = CRMSyncResult(
            email_id=email_id,
            contact_id="contact-001",
            activity_id="act-002",
            operations=ops,
            overall_success=True,
        )
        assert result.email_id == email_id
        assert result.contact_id == "contact-001"
        assert result.activity_id == "act-002"
        assert result.lead_id is None
        assert len(result.operations) == 2
        assert result.overall_success is True
        assert result.paused_for_auth is False

    def test_crm_sync_result_optional_ids_default_none(self) -> None:
        email_id = uuid.uuid4()
        result = CRMSyncResult(
            email_id=email_id,
            operations=[],
            overall_success=False,
        )
        assert result.contact_id is None
        assert result.activity_id is None
        assert result.lead_id is None

    def test_crm_sync_result_paused_for_auth_default_false(self) -> None:
        result = CRMSyncResult(
            email_id=uuid.uuid4(),
            operations=[],
            overall_success=False,
        )
        assert result.paused_for_auth is False

    def test_crm_sync_result_paused_for_auth_explicit_true(self) -> None:
        result = CRMSyncResult(
            email_id=uuid.uuid4(),
            operations=[],
            overall_success=False,
            paused_for_auth=True,
        )
        assert result.paused_for_auth is True

    def test_crm_sync_result_operations_list_preserved(self) -> None:
        ops = [
            CRMOperationStatus(operation="contact_lookup", success=True),
            CRMOperationStatus(operation="contact_create", success=True, crm_id="c-1"),
            CRMOperationStatus(operation="activity_log", success=False, error="Timeout"),
        ]
        result = CRMSyncResult(
            email_id=uuid.uuid4(),
            operations=ops,
            overall_success=False,
        )
        assert len(result.operations) == 3
        assert result.operations[0].operation == "contact_lookup"
        assert result.operations[1].crm_id == "c-1"
        assert result.operations[2].error == "Timeout"
