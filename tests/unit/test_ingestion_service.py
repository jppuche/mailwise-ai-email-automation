"""Tests for IngestionService — mocked adapter, DB session, and Redis."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.adapters.email.exceptions import EmailAdapterError, FetchError
from src.adapters.email.schemas import (
    AttachmentData as AdapterAttachmentData,
)
from src.adapters.email.schemas import (
    EmailMessage,
)
from src.adapters.email.schemas import (
    RecipientData as AdapterRecipientData,
)
from src.core.config import Settings
from src.services.ingestion import IngestionService, _map_attachments, _map_recipients
from src.services.schemas.ingestion import (
    FailureReason,
    SkipReason,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 2, 28, 12, 0, 0, tzinfo=UTC)
_EARLIER = _NOW - timedelta(hours=1)
_LATER = _NOW + timedelta(hours=1)


_DEFAULT_TO = [AdapterRecipientData(email="to@example.com", name="Recipient")]


def _make_email_message(
    *,
    gmail_message_id: str = "gmail-msg-001",
    thread_id: str | None = None,
    subject: str = "Test Subject",
    from_address: str = "sender@example.com",
    received_at: datetime = _NOW,
    body_plain: str | None = "Hello, this is a test email.",
    snippet: str | None = "Hello, this is a test",
    to_addresses: list[AdapterRecipientData] | None = None,
    cc_addresses: list[AdapterRecipientData] | None = None,
    attachments: list[AdapterAttachmentData] | None = None,
    provider_labels: list[str] | None = None,
) -> EmailMessage:
    return EmailMessage(
        id=gmail_message_id,
        gmail_message_id=gmail_message_id,
        thread_id=thread_id,
        subject=subject,
        from_address=from_address,
        to_addresses=_DEFAULT_TO if to_addresses is None else to_addresses,
        cc_addresses=[] if cc_addresses is None else cc_addresses,
        body_plain=body_plain,
        body_html=None,
        snippet=snippet,
        received_at=received_at,
        attachments=[] if attachments is None else attachments,
        provider_labels=["INBOX"] if provider_labels is None else provider_labels,
    )


def _make_settings(**overrides: object) -> Settings:
    defaults = {
        "database_url": "postgresql+asyncpg://test:test@localhost/test",
        "database_url_sync": "postgresql+psycopg2://test:test@localhost/test",
        "jwt_secret_key": "test-secret",
        "redis_url": "redis://localhost:6379/0",
        "ingestion_batch_size": 50,
        "max_body_length": 4000,
        "snippet_length": 200,
        "ingestion_lock_ttl_seconds": 300,
        "ingestion_lock_key_prefix": "mailwise:ingest:lock",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    return _make_settings()


@pytest.fixture
def mock_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.fetch_new_messages.return_value = [_make_email_message()]
    return adapter


@pytest.fixture
def mock_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.set.return_value = True  # lock acquired
    redis.delete.return_value = None
    return redis


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    # Default: no duplicates, no thread conflicts
    scalar_mock = MagicMock()
    scalar_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = scalar_mock
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def service(
    mock_adapter: MagicMock,
    mock_session: AsyncMock,
    mock_redis: AsyncMock,
    settings: Settings,
) -> IngestionService:
    return IngestionService(
        adapter=mock_adapter,
        session=mock_session,
        redis=mock_redis,
        settings=settings,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_single_email_ingested(
        self, service: IngestionService, mock_adapter: MagicMock
    ) -> None:
        mock_adapter.fetch_new_messages.return_value = [_make_email_message()]

        result = await service.ingest_batch("account-1", since=_EARLIER)

        assert result.lock_acquired is True
        assert result.ingested == 1
        assert result.skipped == 0
        assert result.failed == 0
        assert len(result.results) == 1
        assert result.results[0].is_ingested is True
        assert result.results[0].provider_message_id == "gmail-msg-001"

    @pytest.mark.asyncio
    async def test_multiple_emails_ingested(
        self, service: IngestionService, mock_adapter: MagicMock
    ) -> None:
        mock_adapter.fetch_new_messages.return_value = [
            _make_email_message(gmail_message_id=f"msg-{i}") for i in range(3)
        ]

        result = await service.ingest_batch("account-1", since=_EARLIER)

        assert result.ingested == 3
        assert result.skipped == 0
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_empty_batch(self, service: IngestionService, mock_adapter: MagicMock) -> None:
        mock_adapter.fetch_new_messages.return_value = []

        result = await service.ingest_batch("account-1", since=_EARLIER)

        assert result.lock_acquired is True
        assert result.ingested == 0
        assert result.skipped == 0
        assert result.failed == 0
        assert len(result.results) == 0

    @pytest.mark.asyncio
    async def test_account_id_in_result(self, service: IngestionService) -> None:
        result = await service.ingest_batch("my-account", since=_EARLIER)
        assert result.account_id == "my-account"


# ---------------------------------------------------------------------------
# Lock behavior
# ---------------------------------------------------------------------------


class TestLockBehavior:
    @pytest.mark.asyncio
    async def test_lock_not_acquired(
        self, service: IngestionService, mock_redis: AsyncMock
    ) -> None:
        mock_redis.set.return_value = None  # lock NOT acquired

        result = await service.ingest_batch("account-1", since=_EARLIER)

        assert result.lock_acquired is False
        assert result.ingested == 0
        assert len(result.results) == 0

    @pytest.mark.asyncio
    async def test_lock_released_on_success(
        self, service: IngestionService, mock_redis: AsyncMock, settings: Settings
    ) -> None:
        await service.ingest_batch("account-1", since=_EARLIER)

        lock_key = f"{settings.ingestion_lock_key_prefix}:account-1"
        mock_redis.set.assert_called_once_with(
            lock_key, "1", nx=True, ex=settings.ingestion_lock_ttl_seconds
        )
        mock_redis.delete.assert_called_once_with(lock_key)

    @pytest.mark.asyncio
    async def test_lock_released_on_adapter_failure(
        self,
        service: IngestionService,
        mock_adapter: MagicMock,
        mock_redis: AsyncMock,
        settings: Settings,
    ) -> None:
        mock_adapter.fetch_new_messages.side_effect = FetchError("timeout")

        await service.ingest_batch("account-1", since=_EARLIER)

        lock_key = f"{settings.ingestion_lock_key_prefix}:account-1"
        mock_redis.delete.assert_called_once_with(lock_key)

    @pytest.mark.asyncio
    async def test_lock_released_on_unexpected_error(
        self,
        service: IngestionService,
        mock_adapter: MagicMock,
        mock_redis: AsyncMock,
    ) -> None:
        mock_adapter.fetch_new_messages.side_effect = RuntimeError("unexpected")

        with pytest.raises(RuntimeError, match="unexpected"):
            await service.ingest_batch("account-1", since=_EARLIER)

        # Lock still released via finally
        mock_redis.delete.assert_called_once()


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_duplicate_skipped(
        self, service: IngestionService, mock_session: AsyncMock
    ) -> None:
        # First execute returns existing email ID (dedup check)
        existing_mock = MagicMock()
        existing_mock.scalar_one_or_none.return_value = uuid.uuid4()
        mock_session.execute.return_value = existing_mock

        result = await service.ingest_batch("account-1", since=_EARLIER)

        assert result.skipped == 1
        assert result.results[0].skip_reason == SkipReason.DUPLICATE

    @pytest.mark.asyncio
    async def test_integrity_error_treated_as_duplicate(
        self,
        service: IngestionService,
        mock_session: AsyncMock,
    ) -> None:
        # Dedup check passes but commit raises IntegrityError (race condition)
        no_existing = MagicMock()
        no_existing.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = no_existing
        mock_session.commit.side_effect = IntegrityError(
            "duplicate", params=None, orig=Exception("unique violation")
        )

        result = await service.ingest_batch("account-1", since=_EARLIER)

        assert result.skipped == 1
        assert result.results[0].skip_reason == SkipReason.DUPLICATE


# ---------------------------------------------------------------------------
# Thread awareness
# ---------------------------------------------------------------------------


class TestThreadAwareness:
    @pytest.mark.asyncio
    async def test_thread_not_newest_skipped(
        self,
        service: IngestionService,
        mock_adapter: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        mock_adapter.fetch_new_messages.return_value = [
            _make_email_message(
                gmail_message_id="old-msg",
                thread_id="thread-1",
                received_at=_EARLIER,
            )
        ]

        # execute call sequence:
        # 1st: dedup check → no existing
        # 2nd: thread check → existing newer message
        dedup_result = MagicMock()
        dedup_result.scalar_one_or_none.return_value = None

        thread_result = MagicMock()
        thread_result.scalar_one_or_none.return_value = _LATER  # newer exists

        mock_session.execute.side_effect = [dedup_result, thread_result]

        result = await service.ingest_batch("account-1", since=_EARLIER)

        assert result.skipped == 1
        assert result.results[0].skip_reason == SkipReason.THREAD_NOT_NEWEST

    @pytest.mark.asyncio
    async def test_thread_newest_ingested(
        self,
        service: IngestionService,
        mock_adapter: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        mock_adapter.fetch_new_messages.return_value = [
            _make_email_message(
                gmail_message_id="new-msg",
                thread_id="thread-1",
                received_at=_LATER,
            )
        ]

        # 1st: dedup → no existing
        # 2nd: thread → existing older message
        dedup_result = MagicMock()
        dedup_result.scalar_one_or_none.return_value = None

        thread_result = MagicMock()
        thread_result.scalar_one_or_none.return_value = _EARLIER  # older

        mock_session.execute.side_effect = [dedup_result, thread_result]

        result = await service.ingest_batch("account-1", since=_EARLIER)

        assert result.ingested == 1

    @pytest.mark.asyncio
    async def test_no_thread_id_skips_thread_check(
        self,
        service: IngestionService,
        mock_adapter: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        mock_adapter.fetch_new_messages.return_value = [_make_email_message(thread_id=None)]

        # Only dedup check, no thread check
        dedup_result = MagicMock()
        dedup_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = dedup_result

        result = await service.ingest_batch("account-1", since=_EARLIER)

        assert result.ingested == 1
        # execute called once for dedup only (no thread check)
        assert mock_session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_thread_no_existing_messages(
        self,
        service: IngestionService,
        mock_adapter: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        mock_adapter.fetch_new_messages.return_value = [_make_email_message(thread_id="thread-new")]

        # 1st: dedup → no existing
        # 2nd: thread → no existing in thread
        dedup_result = MagicMock()
        dedup_result.scalar_one_or_none.return_value = None

        thread_result = MagicMock()
        thread_result.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [dedup_result, thread_result]

        result = await service.ingest_batch("account-1", since=_EARLIER)

        assert result.ingested == 1


# ---------------------------------------------------------------------------
# Per-email isolation
# ---------------------------------------------------------------------------


class TestPerEmailIsolation:
    @pytest.mark.asyncio
    async def test_db_error_on_second_email_others_succeed(
        self,
        service: IngestionService,
        mock_adapter: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        mock_adapter.fetch_new_messages.return_value = [
            _make_email_message(gmail_message_id="msg-1"),
            _make_email_message(gmail_message_id="msg-2"),
            _make_email_message(gmail_message_id="msg-3"),
        ]

        # Dedup check always passes
        dedup_ok = MagicMock()
        dedup_ok.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = dedup_ok

        # commit: success, failure, success
        call_count = 0

        async def commit_side_effect() -> None:
            nonlocal call_count
            call_count += 1
            # msg-2 has commits at positions 3 and 4 (1-indexed)
            # msg-1: commits 1,2; msg-2: commits 3,4; msg-3: commits 5,6
            if call_count == 3:
                raise SQLAlchemyError("connection lost")

        mock_session.commit = AsyncMock(side_effect=commit_side_effect)

        result = await service.ingest_batch("account-1", since=_EARLIER)

        assert result.ingested == 2
        assert result.failed == 1
        assert result.results[1].failure_reason == FailureReason.DB_WRITE_ERROR

    @pytest.mark.asyncio
    async def test_transition_commit_failure(
        self,
        service: IngestionService,
        mock_adapter: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        mock_adapter.fetch_new_messages.return_value = [
            _make_email_message(gmail_message_id="msg-1"),
        ]

        dedup_ok = MagicMock()
        dedup_ok.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = dedup_ok

        # First commit (FETCHED) succeeds, second commit (SANITIZED) fails
        call_count = 0

        async def commit_side_effect() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise SQLAlchemyError("transition commit failed")

        mock_session.commit = AsyncMock(side_effect=commit_side_effect)

        result = await service.ingest_batch("account-1", since=_EARLIER)

        assert result.failed == 1
        assert result.results[0].failure_reason == FailureReason.DB_TRANSITION_ERROR
        # email_id is still set because FETCHED commit succeeded
        assert result.results[0].email_id is not None


# ---------------------------------------------------------------------------
# Adapter failure
# ---------------------------------------------------------------------------


class TestAdapterFailure:
    @pytest.mark.asyncio
    async def test_fetch_error_returns_empty_batch(
        self, service: IngestionService, mock_adapter: MagicMock
    ) -> None:
        mock_adapter.fetch_new_messages.side_effect = FetchError("API error")

        result = await service.ingest_batch("account-1", since=_EARLIER)

        assert result.lock_acquired is True
        assert result.ingested == 0
        assert len(result.results) == 0

    @pytest.mark.asyncio
    async def test_email_adapter_error_caught(
        self, service: IngestionService, mock_adapter: MagicMock
    ) -> None:
        mock_adapter.fetch_new_messages.side_effect = EmailAdapterError("auth failed")

        result = await service.ingest_batch("account-1", since=_EARLIER)

        assert result.ingested == 0
        assert len(result.results) == 0


# ---------------------------------------------------------------------------
# Two commits per email
# ---------------------------------------------------------------------------


class TestTwoCommitsPerEmail:
    @pytest.mark.asyncio
    async def test_fetched_then_sanitized_commit(
        self,
        service: IngestionService,
        mock_adapter: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        mock_adapter.fetch_new_messages.return_value = [_make_email_message()]

        dedup_ok = MagicMock()
        dedup_ok.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = dedup_ok

        result = await service.ingest_batch("account-1", since=_EARLIER)

        assert result.ingested == 1
        # Two commits: one for FETCHED insert, one for SANITIZED transition
        assert mock_session.commit.call_count == 2

    @pytest.mark.asyncio
    async def test_session_add_called_before_first_commit(
        self,
        service: IngestionService,
        mock_adapter: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        mock_adapter.fetch_new_messages.return_value = [_make_email_message()]

        dedup_ok = MagicMock()
        dedup_ok.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = dedup_ok

        await service.ingest_batch("account-1", since=_EARLIER)

        mock_session.add.assert_called_once()


# ---------------------------------------------------------------------------
# Recipient and attachment mapping
# ---------------------------------------------------------------------------


class TestMapping:
    def test_map_recipients_to_and_cc(self) -> None:
        msg = _make_email_message(
            to_addresses=[
                AdapterRecipientData(email="to1@ex.com", name="To One"),
                AdapterRecipientData(email="to2@ex.com", name=None),
            ],
            cc_addresses=[
                AdapterRecipientData(email="cc1@ex.com", name="CC One"),
            ],
        )

        result = _map_recipients(msg)

        assert len(result) == 3
        assert result[0] == {"email": "to1@ex.com", "name": "To One", "type": "to"}
        assert result[1] == {"email": "to2@ex.com", "name": "", "type": "to"}
        assert result[2] == {"email": "cc1@ex.com", "name": "CC One", "type": "cc"}

    def test_map_recipients_empty(self) -> None:
        msg = _make_email_message(to_addresses=[], cc_addresses=[])
        result = _map_recipients(msg)
        assert result == []

    def test_map_attachments(self) -> None:
        msg = _make_email_message(
            attachments=[
                AdapterAttachmentData(
                    filename="doc.pdf",
                    mime_type="application/pdf",
                    size_bytes=1024,
                    attachment_id="att-1",
                ),
            ]
        )

        result = _map_attachments(msg)

        assert len(result) == 1
        assert result[0] == {
            "filename": "doc.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 1024,
            "attachment_id": "att-1",
        }

    def test_map_attachments_empty(self) -> None:
        msg = _make_email_message(attachments=[])
        result = _map_attachments(msg)
        assert result == []


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------


class TestSanitization:
    @pytest.mark.asyncio
    async def test_body_sanitized(
        self,
        service: IngestionService,
        mock_adapter: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        mock_adapter.fetch_new_messages.return_value = [
            _make_email_message(body_plain="<b>Bold</b> text")
        ]

        dedup_ok = MagicMock()
        dedup_ok.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = dedup_ok

        await service.ingest_batch("account-1", since=_EARLIER)

        # Verify the Email object passed to session.add has sanitized body
        added_email = mock_session.add.call_args[0][0]
        # body_plain goes through sanitize_email_body with strip_html=True (default)
        assert "<b>" not in (added_email.body_plain or "")

    @pytest.mark.asyncio
    async def test_none_body_handled(
        self,
        service: IngestionService,
        mock_adapter: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        mock_adapter.fetch_new_messages.return_value = [
            _make_email_message(body_plain=None, snippet=None)
        ]

        dedup_ok = MagicMock()
        dedup_ok.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = dedup_ok

        await service.ingest_batch("account-1", since=_EARLIER)

        added_email = mock_session.add.call_args[0][0]
        # sanitize_email_body("") returns SanitizedText("") → None check
        assert added_email.body_plain is None
        assert added_email.snippet is None


# ---------------------------------------------------------------------------
# Dedup query failure
# ---------------------------------------------------------------------------


class TestDedupQueryFailure:
    @pytest.mark.asyncio
    async def test_dedup_query_db_error(
        self,
        service: IngestionService,
        mock_adapter: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        mock_adapter.fetch_new_messages.return_value = [_make_email_message()]
        mock_session.execute.side_effect = SQLAlchemyError("connection reset")

        result = await service.ingest_batch("account-1", since=_EARLIER)

        assert result.failed == 1
        assert result.results[0].failure_reason == FailureReason.DB_WRITE_ERROR
        mock_session.rollback.assert_called()
