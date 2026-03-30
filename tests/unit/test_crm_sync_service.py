"""Tests for CRMSyncService — mocked CRM adapter + mocked AsyncSession.

Coverage targets:
  1. Happy path: lookup succeeds, activity logged → overall_success=True
  2. No contact + auto_create=False → no activity/lead ops
  3. No contact + auto_create=True → create_contact called, activity logged
  4. Activity log fails (CRMAdapterError) → contact_id preserved, overall_success=False
  5. CRMAuthError on lookup → pytest.raises(CRMAuthError)
  6. CRMRateLimitError on lookup → pytest.raises(CRMRateLimitError)
  7. CRMAdapterError on activity → lead create still attempts (create_lead=True)
  8. Idempotency: existing SYNCED record → cached result, adapter.lookup_contact not called
  9. Idempotency: existing FAILED record → lookup proceeds normally
  10. DuplicateContactError on create → re-lookup succeeds, contact_id obtained
  11. Field update failure → recorded in operations, other updates continue
  12. Snippet truncated to activity_snippet_length
  13. Empty field_updates → no field_update ops in result

Mocking strategy:
  - CRM adapter: AsyncMock(spec=CRMAdapter) with configured return values.
  - DB session: AsyncMock with scalar_one_or_none / side_effect patterns.
  - ORM models: MagicMock() — SQLAlchemy ORM objects require live DB mapper.
    Never use Model.__new__() (raises InstrumentedAttribute errors).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.crm.base import CRMAdapter
from src.adapters.crm.exceptions import (
    CRMAuthError,
    CRMConnectionError,
    CRMRateLimitError,
    DuplicateContactError,
)
from src.adapters.crm.schemas import ActivityId, Contact, LeadId
from src.models.crm_sync import CRMSyncStatus
from src.services.crm_sync import CRMSyncService, _compute_overall_success
from src.services.schemas.crm_sync import (
    CRMOperationStatus,
    CRMSyncConfig,
    CRMSyncRequest,
    CRMSyncResult,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EMAIL_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_CONTACT_ID = "12345"
_ACTIVITY_ID = "act-001"
_LEAD_ID = "lead-001"
_SENDER_EMAIL = "test@example.com"
_SENDER_NAME = "Test User"
_SUBJECT = "Help with order"
_SNIPPET = "I need help with my order, please respond soon."
_RECEIVED_AT = datetime(2026, 2, 28, 10, 0, 0, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _make_config(
    *,
    auto_create_contacts: bool = False,
    activity_snippet_length: int = 200,
    retry_max: int = 3,
    backoff_base_seconds: int = 60,
) -> CRMSyncConfig:
    return CRMSyncConfig(
        auto_create_contacts=auto_create_contacts,
        activity_snippet_length=activity_snippet_length,
        retry_max=retry_max,
        backoff_base_seconds=backoff_base_seconds,
    )


def _make_request(
    *,
    email_id: uuid.UUID = _EMAIL_ID,
    sender_email: str = _SENDER_EMAIL,
    sender_name: str | None = _SENDER_NAME,
    subject: str = _SUBJECT,
    snippet: str = _SNIPPET,
    classification_action: str = "reply_needed",
    classification_type: str = "customer_support",
    received_at: datetime = _RECEIVED_AT,
    create_lead: bool = False,
    field_updates: dict[str, str] | None = None,
) -> CRMSyncRequest:
    return CRMSyncRequest(
        email_id=email_id,
        sender_email=sender_email,
        sender_name=sender_name,
        subject=subject,
        snippet=snippet,
        classification_action=classification_action,
        classification_type=classification_type,
        received_at=received_at,
        create_lead=create_lead,
        field_updates=field_updates if field_updates is not None else {},
    )


def _make_adapter() -> AsyncMock:
    """Build a mock CRMAdapter with standard happy-path return values."""
    adapter = AsyncMock(spec=CRMAdapter)
    adapter.lookup_contact.return_value = Contact(
        id=_CONTACT_ID,
        email=_SENDER_EMAIL,
    )
    adapter.log_activity.return_value = ActivityId(_ACTIVITY_ID)
    adapter.create_lead.return_value = LeadId(_LEAD_ID)
    adapter.create_contact.return_value = Contact(
        id="99999",
        email=_SENDER_EMAIL,
    )
    # update_field returns None
    adapter.update_field.return_value = None
    return adapter


def _make_db_no_record() -> AsyncMock:
    """Build an AsyncMock DB where idempotency check returns no existing record."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=scalar_result)
    return db


def _make_db_with_record(
    *,
    status: CRMSyncStatus = CRMSyncStatus.SYNCED,
    contact_id: str | None = _CONTACT_ID,
    activity_id: str | None = _ACTIVITY_ID,
    lead_id: str | None = None,
) -> AsyncMock:
    """Build an AsyncMock DB with an existing CRMSyncRecord."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    mock_record = MagicMock()
    mock_record.status = status
    mock_record.contact_id = contact_id
    mock_record.activity_id = activity_id
    mock_record.lead_id = lead_id

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = mock_record
    db.execute = AsyncMock(return_value=scalar_result)
    return db


def _make_service(
    *,
    adapter: AsyncMock | None = None,
    config: CRMSyncConfig | None = None,
) -> CRMSyncService:
    return CRMSyncService(
        crm_adapter=adapter if adapter is not None else _make_adapter(),
        config=config if config is not None else _make_config(),
    )


# ---------------------------------------------------------------------------
# Unit: _compute_overall_success
# ---------------------------------------------------------------------------


def test_compute_overall_success_all_successful() -> None:
    """All operations succeeded → True."""
    ops = [
        CRMOperationStatus(operation="contact_lookup", success=True),
        CRMOperationStatus(operation="activity_log", success=True),
    ]
    assert _compute_overall_success(ops) is True


def test_compute_overall_success_one_failed() -> None:
    """One failed operation → False."""
    ops = [
        CRMOperationStatus(operation="contact_lookup", success=True),
        CRMOperationStatus(operation="activity_log", success=False, error="timeout"),
    ]
    assert _compute_overall_success(ops) is False


def test_compute_overall_success_all_skipped_returns_false() -> None:
    """All skipped (no meaningful sync) → False."""
    ops = [
        CRMOperationStatus(operation="contact_lookup", success=True, skipped=True),
    ]
    assert _compute_overall_success(ops) is False


def test_compute_overall_success_empty_returns_false() -> None:
    """Empty operations list → False (no sync occurred)."""
    assert _compute_overall_success([]) is False


# ---------------------------------------------------------------------------
# 1. Happy path: lookup succeeds, activity logged → overall_success=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_happy_path_contact_found_activity_logged() -> None:
    """Lookup returns contact, activity logged → overall_success=True, ids populated."""
    adapter = _make_adapter()
    db = _make_db_no_record()
    service = _make_service(adapter=adapter)
    request = _make_request()

    result = await service.sync(request, db)

    assert isinstance(result, CRMSyncResult)
    assert result.email_id == _EMAIL_ID
    assert result.contact_id == _CONTACT_ID
    assert result.activity_id == _ACTIVITY_ID
    assert result.lead_id is None
    assert result.overall_success is True
    assert result.paused_for_auth is False

    # Operations list: contact_lookup + activity_log
    op_names = [op.operation for op in result.operations]
    assert "contact_lookup" in op_names
    assert "activity_log" in op_names

    # Adapter calls
    adapter.lookup_contact.assert_awaited_once_with(_SENDER_EMAIL)
    adapter.log_activity.assert_awaited_once()
    adapter.create_contact.assert_not_awaited()
    adapter.create_lead.assert_not_awaited()

    # DB commit called (record persist)
    db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# 2. No contact + auto_create=False → no activity/lead ops
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_no_contact_auto_create_false_no_downstream_ops() -> None:
    """Lookup returns None + auto_create=False → no activity, no lead, no field ops."""
    adapter = _make_adapter()
    adapter.lookup_contact.return_value = None
    db = _make_db_no_record()
    config = _make_config(auto_create_contacts=False)
    service = _make_service(adapter=adapter, config=config)
    request = _make_request(create_lead=True, field_updates={"hs_lead_status": "NEW"})

    result = await service.sync(request, db)

    assert result.contact_id is None
    assert result.activity_id is None
    assert result.lead_id is None
    assert result.overall_success is False  # no non-skipped successful ops

    # Only lookup operation, nothing else
    op_names = [op.operation for op in result.operations]
    assert op_names == ["contact_lookup"]

    adapter.create_contact.assert_not_awaited()
    adapter.log_activity.assert_not_awaited()
    adapter.create_lead.assert_not_awaited()
    adapter.update_field.assert_not_awaited()


# ---------------------------------------------------------------------------
# 3. No contact + auto_create=True → create_contact called, activity logged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_no_contact_auto_create_true_creates_and_logs() -> None:
    """Lookup returns None + auto_create=True → create contact, then log activity."""
    adapter = _make_adapter()
    adapter.lookup_contact.return_value = None
    created_contact = Contact(id="99999", email=_SENDER_EMAIL)
    adapter.create_contact.return_value = created_contact
    adapter.log_activity.return_value = ActivityId(_ACTIVITY_ID)

    db = _make_db_no_record()
    config = _make_config(auto_create_contacts=True)
    service = _make_service(adapter=adapter, config=config)
    request = _make_request()

    result = await service.sync(request, db)

    assert result.contact_id == "99999"
    assert result.activity_id == _ACTIVITY_ID
    assert result.overall_success is True

    op_names = [op.operation for op in result.operations]
    assert "contact_lookup" in op_names
    assert "contact_create" in op_names
    assert "activity_log" in op_names

    adapter.create_contact.assert_awaited_once()
    adapter.log_activity.assert_awaited_once()


# ---------------------------------------------------------------------------
# 4. Activity log fails (CRMAdapterError) → contact_id preserved, overall_success=False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_activity_log_fails_contact_id_preserved() -> None:
    """Activity log raises CRMAdapterError → contact_id in result, overall_success=False."""
    adapter = _make_adapter()
    adapter.log_activity.side_effect = CRMConnectionError("timeout")

    db = _make_db_no_record()
    service = _make_service(adapter=adapter)
    request = _make_request()

    result = await service.sync(request, db)

    assert result.contact_id == _CONTACT_ID
    assert result.activity_id is None
    assert result.overall_success is False

    activity_ops = [op for op in result.operations if op.operation == "activity_log"]
    assert len(activity_ops) == 1
    assert activity_ops[0].success is False
    assert "timeout" in (activity_ops[0].error or "")


# ---------------------------------------------------------------------------
# 5. CRMAuthError on lookup → re-raised (pytest.raises)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_crm_auth_error_on_lookup_is_reraised() -> None:
    """CRMAuthError on lookup is never caught by service — propagates to caller."""
    adapter = _make_adapter()
    adapter.lookup_contact.side_effect = CRMAuthError("token revoked")

    db = _make_db_no_record()
    service = _make_service(adapter=adapter)
    request = _make_request()

    with pytest.raises(CRMAuthError, match="token revoked"):
        await service.sync(request, db)

    # DB commit must NOT have been called (no record persisted)
    db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# 6. CRMRateLimitError on lookup → re-raised (pytest.raises)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_crm_rate_limit_error_on_lookup_is_reraised() -> None:
    """CRMRateLimitError on lookup propagates to caller for retry logic."""
    adapter = _make_adapter()
    adapter.lookup_contact.side_effect = CRMRateLimitError("rate limited", retry_after_seconds=30)

    db = _make_db_no_record()
    service = _make_service(adapter=adapter)
    request = _make_request()

    with pytest.raises(CRMRateLimitError):
        await service.sync(request, db)

    db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# 7. CRMAdapterError on activity → lead create still attempts (create_lead=True)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_activity_failure_does_not_skip_lead_create() -> None:
    """Activity log fails → chain continues, lead create still attempted."""
    adapter = _make_adapter()
    adapter.log_activity.side_effect = CRMConnectionError("connection error")
    adapter.create_lead.return_value = LeadId(_LEAD_ID)

    db = _make_db_no_record()
    service = _make_service(adapter=adapter)
    request = _make_request(create_lead=True)

    result = await service.sync(request, db)

    assert result.contact_id == _CONTACT_ID
    assert result.activity_id is None
    assert result.lead_id == _LEAD_ID  # lead was still created

    op_names = [op.operation for op in result.operations]
    assert "lead_create" in op_names

    lead_ops = [op for op in result.operations if op.operation == "lead_create"]
    assert lead_ops[0].success is True

    adapter.create_lead.assert_awaited_once()


# ---------------------------------------------------------------------------
# 8. Idempotency: existing SYNCED record → cached result, no CRM calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_idempotency_synced_record_returns_cached() -> None:
    """Existing SYNCED record → return cached result, zero CRM API calls."""
    adapter = _make_adapter()
    db = _make_db_with_record(
        status=CRMSyncStatus.SYNCED,
        contact_id=_CONTACT_ID,
        activity_id=_ACTIVITY_ID,
    )
    service = _make_service(adapter=adapter)
    request = _make_request()

    result = await service.sync(request, db)

    assert result.contact_id == _CONTACT_ID
    assert result.activity_id == _ACTIVITY_ID
    assert result.overall_success is True  # built from SYNCED record

    # No CRM calls
    adapter.lookup_contact.assert_not_awaited()
    adapter.log_activity.assert_not_awaited()
    adapter.create_contact.assert_not_awaited()

    # No DB commit (no new record written)
    db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# 9. Idempotency: existing FAILED record → lookup proceeds normally
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_idempotency_failed_record_retries_sync() -> None:
    """Existing FAILED record → treat as fresh sync, proceed with CRM calls."""
    adapter = _make_adapter()
    db = _make_db_with_record(
        status=CRMSyncStatus.FAILED,
        contact_id=None,
        activity_id=None,
    )
    service = _make_service(adapter=adapter)
    request = _make_request()

    result = await service.sync(request, db)

    # Lookup was called (not skipped)
    adapter.lookup_contact.assert_awaited_once()
    # A new record is committed
    db.commit.assert_awaited()
    assert result.contact_id == _CONTACT_ID


# ---------------------------------------------------------------------------
# 10. DuplicateContactError on create → re-lookup succeeds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_duplicate_contact_error_re_lookup_succeeds() -> None:
    """DuplicateContactError on create → re-lookup, contact_id obtained."""
    adapter = _make_adapter()
    adapter.lookup_contact.return_value = None  # first lookup returns None
    adapter.create_contact.side_effect = DuplicateContactError(
        "already exists", original_error=None
    )
    # Re-lookup returns the existing contact
    re_lookup_contact = Contact(id=_CONTACT_ID, email=_SENDER_EMAIL)
    adapter.lookup_contact.side_effect = [None, re_lookup_contact]

    db = _make_db_no_record()
    config = _make_config(auto_create_contacts=True)
    service = _make_service(adapter=adapter, config=config)
    request = _make_request()

    result = await service.sync(request, db)

    assert result.contact_id == _CONTACT_ID

    create_ops = [op for op in result.operations if op.operation == "contact_create"]
    assert len(create_ops) == 1
    assert create_ops[0].success is True
    assert create_ops[0].crm_id == _CONTACT_ID

    # lookup_contact called twice: initial + re-lookup
    assert adapter.lookup_contact.await_count == 2


# ---------------------------------------------------------------------------
# 11. Field update failure → recorded, other updates continue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_field_update_partial_failure_continues() -> None:
    """First field update fails → recorded, second field update still attempted."""
    adapter = _make_adapter()
    adapter.update_field.side_effect = [
        CRMConnectionError("timeout on first field"),
        None,  # second field succeeds
    ]

    db = _make_db_no_record()
    service = _make_service(adapter=adapter)
    request = _make_request(field_updates={"hs_lead_status": "QUALIFIED", "industry": "Technology"})

    result = await service.sync(request, db)

    field_ops = [op for op in result.operations if op.operation == "field_update"]
    assert len(field_ops) == 2

    failed_ops = [op for op in field_ops if not op.success]
    success_ops = [op for op in field_ops if op.success]
    assert len(failed_ops) == 1
    assert len(success_ops) == 1
    assert "timeout on first field" in (failed_ops[0].error or "")

    # overall_success is False because one field update failed
    assert result.overall_success is False

    # update_field was called twice
    assert adapter.update_field.await_count == 2


# ---------------------------------------------------------------------------
# 12. Snippet truncated to activity_snippet_length
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_snippet_truncated_to_config_length() -> None:
    """Snippet passed to log_activity is truncated to activity_snippet_length."""
    adapter = _make_adapter()
    db = _make_db_no_record()
    config = _make_config(activity_snippet_length=10)
    service = _make_service(adapter=adapter, config=config)

    long_snippet = "A" * 500
    request = _make_request(snippet=long_snippet)

    await service.sync(request, db)

    adapter.log_activity.assert_awaited_once()
    call_args = adapter.log_activity.call_args
    activity_data = call_args.args[1]
    assert len(activity_data.snippet) == 10
    assert activity_data.snippet == "A" * 10


# ---------------------------------------------------------------------------
# 13. Empty field_updates → no field_update ops in result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_empty_field_updates_no_field_ops() -> None:
    """Empty field_updates dict → no field_update ops in result."""
    adapter = _make_adapter()
    db = _make_db_no_record()
    service = _make_service(adapter=adapter)
    request = _make_request(field_updates={})

    result = await service.sync(request, db)

    field_ops = [op for op in result.operations if op.operation == "field_update"]
    assert len(field_ops) == 0

    adapter.update_field.assert_not_awaited()


# ---------------------------------------------------------------------------
# Extra: CRMAuthError during activity_log is re-raised
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_auth_error_during_activity_log_is_reraised() -> None:
    """CRMAuthError during activity log propagates — never silenced."""
    adapter = _make_adapter()
    adapter.log_activity.side_effect = CRMAuthError("token expired")

    db = _make_db_no_record()
    service = _make_service(adapter=adapter)
    request = _make_request()

    with pytest.raises(CRMAuthError, match="token expired"):
        await service.sync(request, db)


# ---------------------------------------------------------------------------
# Extra: CRMAuthError during field update is re-raised (aborts remaining)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_auth_error_during_field_update_is_reraised() -> None:
    """CRMAuthError during field update propagates — remaining fields not attempted."""
    adapter = _make_adapter()
    adapter.update_field.side_effect = CRMAuthError("token expired on update")

    db = _make_db_no_record()
    service = _make_service(adapter=adapter)
    request = _make_request(field_updates={"field_one": "val1", "field_two": "val2"})

    with pytest.raises(CRMAuthError):
        await service.sync(request, db)

    # Only one update_field call before the exception
    assert adapter.update_field.await_count == 1
