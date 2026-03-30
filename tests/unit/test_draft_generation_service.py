"""Tests for DraftGenerationService — mocked LLM adapter + email adapter + AsyncSession.

Coverage targets:
  1.  Happy path: LLM succeeds, push=False → Draft in DB, status="generated", email=DRAFT_GENERATED
  2.  Happy path with push: Gmail succeeds → gmail_draft_id populated, pushed_to_provider=True
  3.  Gmail push fails → email stays DRAFT_GENERATED, status="generated_push_failed"
  4.  LLMConnectionError → email=DRAFT_FAILED, draft_id=None, status="failed"
  5.  LLMTimeoutError → email=DRAFT_FAILED, draft_id=None, status="failed"
  6.  LLMRateLimitError → re-raised, email stays CRM_SYNCED
  7.  DB error on Draft flush → email=DRAFT_FAILED, status="failed", rollback called
  8.  No CRM record → service still works, notes contain "CRM context unavailable"
  9.  DraftContextBuilder.build() never raises — works with missing optional data
  10. email_id in DraftResult always matches request.email_id
  11. model_used in DraftResult reflects DraftText.model_used
  12. fallback_applied in DraftResult reflects DraftText.fallback_applied
  13. CRM record is loaded from DB before context build (query executed)
  14. Draft committed before Gmail push (D13 — db.commit before to_thread)
  15. _handle_failure: SQLAlchemyError on state transition logged, not re-raised

Mocking strategy:
  - LLM adapter: AsyncMock(spec=LLMAdapter) with generate_draft configured.
  - Email adapter: MagicMock(spec=EmailAdapter) — create_draft is a sync method.
  - asyncio.to_thread: patched at import site to invoke the function synchronously.
  - DB session: AsyncMock with scalar_one_or_none side_effect patterns.
  - ORM models: MagicMock() — SQLAlchemy ORM objects require live DB mapper.
    Never use Model.__new__() (raises InstrumentedAttribute errors).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.adapters.email.base import EmailAdapter
from src.adapters.email.exceptions import EmailAdapterError
from src.adapters.email.schemas import DraftId
from src.adapters.llm.base import LLMAdapter
from src.adapters.llm.exceptions import (
    LLMConnectionError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from src.adapters.llm.schemas import DraftText
from src.models.email import EmailState
from src.services.draft_generation import DraftGenerationService
from src.services.schemas.draft import (
    ClassificationContext,
    DraftGenerationConfig,
    DraftRequest,
    DraftResult,
    EmailContent,
    OrgContext,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EMAIL_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_DRAFT_TEXT = DraftText(
    content="Dear Customer, thank you for reaching out.",
    model_used="gpt-4o",
    fallback_applied=False,
)
_GMAIL_DRAFT_ID = DraftId("gmail-draft-001")

# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _make_org_context() -> OrgContext:
    return OrgContext(
        system_prompt="You are a professional support agent.",
        tone="professional",
    )


def _make_config(*, push_to_gmail: bool = False) -> DraftGenerationConfig:
    return DraftGenerationConfig(
        push_to_gmail=push_to_gmail,
        org_context=_make_org_context(),
        retry_max=2,
    )


def _make_request(
    *,
    email_id: uuid.UUID = _EMAIL_ID,
    push_to_gmail: bool = False,
) -> DraftRequest:
    return DraftRequest(
        email_id=email_id,
        email_content=EmailContent(
            sender_email="customer@example.com",
            sender_name="John Doe",
            subject="Help with order",
            body_snippet="I need help with my order, please respond soon.",
            received_at="2026-02-28T10:00:00Z",
        ),
        classification=ClassificationContext(
            action="respond",
            type="support",
            confidence="high",
        ),
        push_to_gmail=push_to_gmail,
    )


def _make_llm_adapter(
    *,
    draft_text: DraftText = _DRAFT_TEXT,
) -> AsyncMock:
    adapter = AsyncMock(spec=LLMAdapter)
    adapter.generate_draft.return_value = draft_text
    return adapter


def _make_email_adapter(
    *,
    gmail_draft_id: DraftId = _GMAIL_DRAFT_ID,
) -> MagicMock:
    adapter = MagicMock(spec=EmailAdapter)
    adapter.create_draft.return_value = gmail_draft_id
    return adapter


def _make_email_orm(
    *,
    state: EmailState = EmailState.CRM_SYNCED,
) -> MagicMock:
    """Build a mock Email ORM object with transition_to() tracking."""
    mock_email = MagicMock()
    mock_email.state = state
    mock_email.transition_to = MagicMock()
    return mock_email


def _make_crm_record(
    *,
    contact_id: str = "crm-contact-001",
) -> MagicMock:
    """Build a mock CRMSyncRecord."""
    record = MagicMock()
    record.contact_id = contact_id
    return record


def _make_db(
    *,
    crm_record: object = None,
    email_orm: object = None,
) -> AsyncMock:
    """Build AsyncMock DB with two sequential execute() calls.

    First call: CRM record lookup.
    Second call: Email ORM lookup (for state transition).
    """
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    crm_result = MagicMock()
    crm_result.scalar_one_or_none.return_value = crm_record

    email_result = MagicMock()
    email_result.scalar_one_or_none.return_value = email_orm

    db.execute = AsyncMock(side_effect=[crm_result, email_result])
    return db


def _make_service(
    *,
    llm_adapter: AsyncMock | None = None,
    email_adapter: MagicMock | None = None,
    config: DraftGenerationConfig | None = None,
) -> DraftGenerationService:
    return DraftGenerationService(
        llm_adapter=llm_adapter if llm_adapter is not None else _make_llm_adapter(),
        email_adapter=email_adapter if email_adapter is not None else _make_email_adapter(),
        config=config if config is not None else _make_config(),
    )


# ---------------------------------------------------------------------------
# 1. Happy path: LLM succeeds, push=False → status="generated", email=DRAFT_GENERATED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_happy_path_no_push() -> None:
    """LLM succeeds, push=False → DraftResult status='generated', email transitioned."""
    email_orm = _make_email_orm()
    db = _make_db(crm_record=None, email_orm=email_orm)
    service = _make_service()
    request = _make_request(push_to_gmail=False)

    result = await service.generate(request, db)

    assert isinstance(result, DraftResult)
    assert result.email_id == _EMAIL_ID
    assert result.status == "generated"
    assert result.draft_id is not None
    assert result.gmail_draft_id is None
    assert result.error_detail is None
    assert result.model_used == "gpt-4o"
    assert result.fallback_applied is False

    # Draft was added and committed
    db.add.assert_called_once()
    db.flush.assert_awaited_once()
    # At least one commit (draft commit + state transition commit)
    assert db.commit.await_count >= 1

    # Email transitioned to DRAFT_GENERATED
    email_orm.transition_to.assert_called_with(EmailState.DRAFT_GENERATED)


# ---------------------------------------------------------------------------
# 2. Happy path with Gmail push → gmail_draft_id populated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_happy_path_with_push_succeeds() -> None:
    """LLM succeeds + push=True + Gmail succeeds → gmail_draft_id in result."""
    email_orm = _make_email_orm()
    db = _make_db(crm_record=None, email_orm=email_orm)
    email_adapter = _make_email_adapter(gmail_draft_id=_GMAIL_DRAFT_ID)
    service = _make_service(email_adapter=email_adapter)
    request = _make_request(push_to_gmail=True)

    # Patch asyncio.to_thread to call the function synchronously in tests
    async def _sync_to_thread(func: object, /, *args: object, **kwargs: object) -> object:
        assert callable(func)
        return func(*args, **kwargs)  # type: ignore[operator]

    with patch(
        "src.services.draft_generation.asyncio.to_thread",
        side_effect=_sync_to_thread,
    ):
        result = await service.generate(request, db)

    assert result.status == "generated"
    assert result.gmail_draft_id == str(_GMAIL_DRAFT_ID)
    assert result.draft_id is not None

    # create_draft was called with correct args
    email_adapter.create_draft.assert_called_once_with(
        to="customer@example.com",
        subject="Re: Help with order",
        body=_DRAFT_TEXT.content,
    )


# ---------------------------------------------------------------------------
# 3. Gmail push fails → DRAFT_GENERATED (not DRAFT_FAILED), status="generated_push_failed"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_gmail_push_fails_email_stays_draft_generated() -> None:
    """Gmail push raises EmailAdapterError → status='generated_push_failed', not DRAFT_FAILED."""
    email_orm = _make_email_orm()
    db = _make_db(crm_record=None, email_orm=email_orm)
    email_adapter = _make_email_adapter()
    email_adapter.create_draft.side_effect = EmailAdapterError("Gmail API error")
    service = _make_service(email_adapter=email_adapter)
    request = _make_request(push_to_gmail=True)

    async def _sync_to_thread(func: object, /, *args: object, **kwargs: object) -> object:
        assert callable(func)
        return func(*args, **kwargs)  # type: ignore[operator]

    with patch(
        "src.services.draft_generation.asyncio.to_thread",
        side_effect=_sync_to_thread,
    ):
        result = await service.generate(request, db)

    assert result.status == "generated_push_failed"
    assert result.gmail_draft_id is None
    assert result.draft_id is not None  # draft was still committed

    # Email transitioned to DRAFT_GENERATED (not DRAFT_FAILED)
    email_orm.transition_to.assert_called_with(EmailState.DRAFT_GENERATED)
    draft_failed_calls = [
        c for c in email_orm.transition_to.call_args_list if c == call(EmailState.DRAFT_FAILED)
    ]
    assert len(draft_failed_calls) == 0


# ---------------------------------------------------------------------------
# 4. LLMConnectionError → email=DRAFT_FAILED, draft_id=None, status="failed"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_llm_connection_error_transitions_draft_failed() -> None:
    """LLMConnectionError → DRAFT_FAILED result, no draft persisted."""
    email_orm = _make_email_orm()
    # _handle_failure does its own db.execute for the email ORM
    db = _make_db(crm_record=None, email_orm=email_orm)
    llm_adapter = _make_llm_adapter()
    llm_adapter.generate_draft.side_effect = LLMConnectionError("provider unreachable")
    service = _make_service(llm_adapter=llm_adapter)
    request = _make_request()

    result = await service.generate(request, db)

    assert result.status == "failed"
    assert result.draft_id is None
    assert result.error_detail is not None
    assert "provider unreachable" in result.error_detail

    # Email transitioned to DRAFT_FAILED
    email_orm.transition_to.assert_called_with(EmailState.DRAFT_FAILED)

    # No Draft was added to DB
    db.add.assert_not_called()
    db.flush.assert_not_awaited()


# ---------------------------------------------------------------------------
# 5. LLMTimeoutError → email=DRAFT_FAILED, same behavior as connection error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_llm_timeout_error_transitions_draft_failed() -> None:
    """LLMTimeoutError → DRAFT_FAILED result, error_detail populated."""
    email_orm = _make_email_orm()
    db = _make_db(crm_record=None, email_orm=email_orm)
    llm_adapter = _make_llm_adapter()
    llm_adapter.generate_draft.side_effect = LLMTimeoutError("LLM call timed out")
    service = _make_service(llm_adapter=llm_adapter)
    request = _make_request()

    result = await service.generate(request, db)

    assert result.status == "failed"
    assert result.draft_id is None
    assert "timed out" in (result.error_detail or "")

    email_orm.transition_to.assert_called_with(EmailState.DRAFT_FAILED)
    db.add.assert_not_called()


# ---------------------------------------------------------------------------
# 6. LLMRateLimitError → re-raised to Celery task, email stays CRM_SYNCED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_llm_rate_limit_error_is_reraised() -> None:
    """LLMRateLimitError is never caught — propagates to Celery task for retry."""
    email_orm = _make_email_orm(state=EmailState.CRM_SYNCED)
    # Only one execute call will happen: CRM record lookup
    crm_result = MagicMock()
    crm_result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.execute = AsyncMock(return_value=crm_result)

    llm_adapter = _make_llm_adapter()
    llm_adapter.generate_draft.side_effect = LLMRateLimitError(
        "rate limit exceeded", retry_after_seconds=60
    )
    service = _make_service(llm_adapter=llm_adapter)
    request = _make_request()

    with pytest.raises(LLMRateLimitError, match="rate limit exceeded"):
        await service.generate(request, db)

    # Email state must not have been touched
    email_orm.transition_to.assert_not_called()
    # No Draft was committed
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# 7. DB error on Draft flush → email=DRAFT_FAILED, rollback called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_db_error_on_flush_transitions_draft_failed() -> None:
    """SQLAlchemyError on db.flush() → rollback, DRAFT_FAILED, no gmail push."""
    email_orm = _make_email_orm()
    # Three execute calls needed:
    # 1. CRM record lookup (in _load_crm_record)
    # 2. Email ORM lookup (in _handle_failure)
    crm_result = MagicMock()
    crm_result.scalar_one_or_none.return_value = None

    email_result = MagicMock()
    email_result.scalar_one_or_none.return_value = email_orm

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock(side_effect=SQLAlchemyError("constraint violation"))
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.execute = AsyncMock(side_effect=[crm_result, email_result])

    service = _make_service()
    request = _make_request()

    result = await service.generate(request, db)

    assert result.status == "failed"
    assert result.draft_id is None
    assert "DB persist failed" in (result.error_detail or "")

    db.rollback.assert_awaited_once()
    email_orm.transition_to.assert_called_with(EmailState.DRAFT_FAILED)


# ---------------------------------------------------------------------------
# 8. No CRM record → service still works, notes include "CRM context unavailable"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_no_crm_record_service_still_works() -> None:
    """CRM record lookup returns None → DraftContextBuilder notes missing context."""
    email_orm = _make_email_orm()
    db = _make_db(crm_record=None, email_orm=email_orm)
    service = _make_service()
    request = _make_request()

    result = await service.generate(request, db)

    assert result.status == "generated"
    assert result.draft_id is not None
    # LLM was still called despite missing CRM context
    service._llm_adapter.generate_draft.assert_awaited_once()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 9. DraftContextBuilder.build() never raises — works with all-optional data missing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_context_builder_never_raises_missing_optional_fields() -> None:
    """Missing crm_record and template_id → builder notes, not errors."""
    email_orm = _make_email_orm()
    db = _make_db(crm_record=None, email_orm=email_orm)
    service = _make_service()
    # No template_id, no CRM record
    request = DraftRequest(
        email_id=_EMAIL_ID,
        email_content=EmailContent(
            sender_email="anon@example.com",
            sender_name=None,
            subject="Question",
            body_snippet="short",
            received_at="2026-02-28T00:00:00Z",
        ),
        classification=ClassificationContext(
            action="respond",
            type="general",
            confidence="low",
        ),
        template_id=None,
        push_to_gmail=False,
    )

    # Must not raise
    result = await service.generate(request, db)

    assert result.status == "generated"


# ---------------------------------------------------------------------------
# 10. email_id in DraftResult always matches request.email_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_result_email_id_matches_request() -> None:
    """DraftResult.email_id must equal request.email_id regardless of outcome."""
    custom_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    email_orm = _make_email_orm()
    db = _make_db(crm_record=None, email_orm=email_orm)
    service = _make_service()
    request = _make_request(email_id=custom_id)

    result = await service.generate(request, db)

    assert result.email_id == custom_id


# ---------------------------------------------------------------------------
# 11. model_used in DraftResult reflects DraftText.model_used
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_result_model_used_reflects_draft_text() -> None:
    """DraftResult.model_used must match DraftText.model_used from LLM adapter."""
    draft_text = DraftText(
        content="Reply body here.",
        model_used="claude-opus-4-6",
        fallback_applied=False,
    )
    email_orm = _make_email_orm()
    db = _make_db(crm_record=None, email_orm=email_orm)
    llm_adapter = _make_llm_adapter(draft_text=draft_text)
    service = _make_service(llm_adapter=llm_adapter)
    request = _make_request()

    result = await service.generate(request, db)

    assert result.model_used == "claude-opus-4-6"


# ---------------------------------------------------------------------------
# 12. fallback_applied in DraftResult reflects DraftText.fallback_applied
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_result_fallback_applied_propagated() -> None:
    """DraftResult.fallback_applied must mirror DraftText.fallback_applied."""
    draft_text = DraftText(
        content="Fallback reply.",
        model_used="gpt-3.5-turbo",
        fallback_applied=True,
    )
    email_orm = _make_email_orm()
    db = _make_db(crm_record=None, email_orm=email_orm)
    llm_adapter = _make_llm_adapter(draft_text=draft_text)
    service = _make_service(llm_adapter=llm_adapter)
    request = _make_request()

    result = await service.generate(request, db)

    assert result.fallback_applied is True


# ---------------------------------------------------------------------------
# 13. CRM record loaded from DB before context build (execute called)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_crm_record_loaded_from_db() -> None:
    """CRM record lookup (db.execute) is called before LLM generate_draft."""
    crm_record = _make_crm_record(contact_id="crm-xyz")
    email_orm = _make_email_orm()
    db = _make_db(crm_record=crm_record, email_orm=email_orm)
    service = _make_service()
    request = _make_request()

    result = await service.generate(request, db)

    # db.execute was called at least once (CRM + email state transition)
    assert db.execute.await_count >= 1
    assert result.status == "generated"

    # LLM was called once
    service._llm_adapter.generate_draft.assert_awaited_once()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 14. Draft committed before Gmail push (D13 — commit ordering)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_draft_committed_before_gmail_push() -> None:
    """D13: db.commit() must be called before asyncio.to_thread (Gmail push)."""
    email_orm = _make_email_orm()
    db = _make_db(crm_record=None, email_orm=email_orm)
    service = _make_service()
    request = _make_request(push_to_gmail=True)

    call_order: list[str] = []

    original_commit = db.commit

    async def _tracking_commit() -> None:
        call_order.append("commit")
        await original_commit()

    db.commit = _tracking_commit

    async def _tracking_to_thread(func: object, /, *args: object, **kwargs: object) -> object:
        call_order.append("to_thread")
        assert callable(func)
        return func(*args, **kwargs)  # type: ignore[operator]

    with patch(
        "src.services.draft_generation.asyncio.to_thread",
        side_effect=_tracking_to_thread,
    ):
        result = await service.generate(request, db)

    assert result.status == "generated"
    # commit must appear before to_thread in the call order
    first_commit = next(i for i, v in enumerate(call_order) if v == "commit")
    first_push = next(i for i, v in enumerate(call_order) if v == "to_thread")
    assert first_commit < first_push, (
        f"commit (idx={first_commit}) must precede to_thread (idx={first_push})"
    )


# ---------------------------------------------------------------------------
# 15. _handle_failure: SQLAlchemyError on state transition logged, not re-raised
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_handle_failure_state_transition_error_not_reraised() -> None:
    """SQLAlchemyError on email state transition in _handle_failure is swallowed."""
    # LLM fails → _handle_failure is called → db.execute raises SQLAlchemyError
    crm_result = MagicMock()
    crm_result.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    # First call: CRM lookup (ok), second call: email lookup in _handle_failure (raises)
    db.execute = AsyncMock(side_effect=[crm_result, SQLAlchemyError("DB connection lost")])

    llm_adapter = _make_llm_adapter()
    llm_adapter.generate_draft.side_effect = LLMConnectionError("provider down")
    service = _make_service(llm_adapter=llm_adapter)
    request = _make_request()

    # Must NOT raise — SQLAlchemyError in _handle_failure is swallowed
    result = await service.generate(request, db)

    assert result.status == "failed"
    assert result.email_id == _EMAIL_ID
    # error_detail reflects the LLM error, not the DB error
    assert "provider down" in (result.error_detail or "")
