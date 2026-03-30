"""Tests for ingestion pipeline schemas (IngestionResult, IngestionBatchResult, enums)."""

from __future__ import annotations

import uuid

import pytest

from src.services.schemas.ingestion import (
    FailureReason,
    IngestionBatchResult,
    IngestionResult,
    SkipReason,
)

# ---------------------------------------------------------------------------
# SkipReason enum
# ---------------------------------------------------------------------------


class TestSkipReason:
    def test_values(self) -> None:
        assert SkipReason.DUPLICATE == "DUPLICATE"
        assert SkipReason.THREAD_NOT_NEWEST == "THREAD_NOT_NEWEST"

    def test_is_str_enum(self) -> None:
        assert isinstance(SkipReason.DUPLICATE, str)

    def test_member_count(self) -> None:
        assert len(SkipReason) == 2


# ---------------------------------------------------------------------------
# FailureReason enum
# ---------------------------------------------------------------------------


class TestFailureReason:
    def test_values(self) -> None:
        assert FailureReason.DB_WRITE_ERROR == "DB_WRITE_ERROR"
        assert FailureReason.DB_TRANSITION_ERROR == "DB_TRANSITION_ERROR"

    def test_is_str_enum(self) -> None:
        assert isinstance(FailureReason.DB_WRITE_ERROR, str)

    def test_member_count(self) -> None:
        assert len(FailureReason) == 2


# ---------------------------------------------------------------------------
# IngestionResult — frozen dataclass
# ---------------------------------------------------------------------------


class TestIngestionResult:
    def test_ingested_result(self) -> None:
        eid = uuid.uuid4()
        result = IngestionResult(provider_message_id="msg-1", email_id=eid)
        assert result.is_ingested is True
        assert result.is_skipped is False
        assert result.is_failed is False
        assert result.email_id == eid
        assert result.provider_message_id == "msg-1"

    def test_skipped_duplicate(self) -> None:
        result = IngestionResult(
            provider_message_id="msg-2",
            skip_reason=SkipReason.DUPLICATE,
        )
        assert result.is_ingested is False
        assert result.is_skipped is True
        assert result.is_failed is False
        assert result.skip_reason == SkipReason.DUPLICATE

    def test_skipped_thread_not_newest(self) -> None:
        result = IngestionResult(
            provider_message_id="msg-3",
            skip_reason=SkipReason.THREAD_NOT_NEWEST,
        )
        assert result.is_skipped is True
        assert result.skip_reason == SkipReason.THREAD_NOT_NEWEST

    def test_failed_db_write(self) -> None:
        result = IngestionResult(
            provider_message_id="msg-4",
            failure_reason=FailureReason.DB_WRITE_ERROR,
            error_detail="connection reset",
        )
        assert result.is_ingested is False
        assert result.is_skipped is False
        assert result.is_failed is True
        assert result.error_detail == "connection reset"

    def test_failed_db_transition(self) -> None:
        result = IngestionResult(
            provider_message_id="msg-5",
            failure_reason=FailureReason.DB_TRANSITION_ERROR,
        )
        assert result.is_failed is True
        assert result.failure_reason == FailureReason.DB_TRANSITION_ERROR

    def test_frozen_immutable(self) -> None:
        result = IngestionResult(provider_message_id="msg-6")
        with pytest.raises(AttributeError):
            result.provider_message_id = "changed"  # type: ignore[misc]

    def test_defaults(self) -> None:
        result = IngestionResult(provider_message_id="msg-7")
        assert result.email_id is None
        assert result.skip_reason is None
        assert result.failure_reason is None
        assert result.error_detail is None
        # With no email_id, skip, or failure → not ingested (edge case)
        assert result.is_ingested is False
        assert result.is_skipped is False
        assert result.is_failed is False

    def test_provider_message_id_required(self) -> None:
        with pytest.raises(TypeError):
            IngestionResult()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# IngestionBatchResult — mutable dataclass
# ---------------------------------------------------------------------------


class TestIngestionBatchResult:
    def test_empty_batch(self) -> None:
        batch = IngestionBatchResult(account_id="test@example.com")
        assert batch.account_id == "test@example.com"
        assert batch.lock_acquired is True
        assert batch.results == []
        assert batch.ingested == 0
        assert batch.skipped == 0
        assert batch.failed == 0

    def test_lock_not_acquired(self) -> None:
        batch = IngestionBatchResult(
            account_id="test@example.com",
            lock_acquired=False,
        )
        assert batch.lock_acquired is False
        assert batch.ingested == 0

    def test_mixed_results(self) -> None:
        batch = IngestionBatchResult(account_id="test@example.com")
        batch.results.append(IngestionResult(provider_message_id="msg-1", email_id=uuid.uuid4()))
        batch.results.append(IngestionResult(provider_message_id="msg-2", email_id=uuid.uuid4()))
        batch.results.append(
            IngestionResult(
                provider_message_id="msg-3",
                skip_reason=SkipReason.DUPLICATE,
            )
        )
        batch.results.append(
            IngestionResult(
                provider_message_id="msg-4",
                failure_reason=FailureReason.DB_WRITE_ERROR,
            )
        )
        assert batch.ingested == 2
        assert batch.skipped == 1
        assert batch.failed == 1
        assert len(batch.results) == 4

    def test_counts_sum_to_total(self) -> None:
        batch = IngestionBatchResult(account_id="acc")
        batch.results = [
            IngestionResult(provider_message_id="a", email_id=uuid.uuid4()),
            IngestionResult(provider_message_id="b", skip_reason=SkipReason.DUPLICATE),
            IngestionResult(
                provider_message_id="c",
                skip_reason=SkipReason.THREAD_NOT_NEWEST,
            ),
            IngestionResult(
                provider_message_id="d",
                failure_reason=FailureReason.DB_WRITE_ERROR,
            ),
            IngestionResult(
                provider_message_id="e",
                failure_reason=FailureReason.DB_TRANSITION_ERROR,
            ),
        ]
        assert batch.ingested + batch.skipped + batch.failed == len(batch.results)

    def test_mutable(self) -> None:
        batch = IngestionBatchResult(account_id="acc")
        batch.lock_acquired = False
        assert batch.lock_acquired is False

    def test_incremental_build(self) -> None:
        batch = IngestionBatchResult(account_id="acc")
        assert batch.ingested == 0
        batch.results.append(IngestionResult(provider_message_id="msg-1", email_id=uuid.uuid4()))
        assert batch.ingested == 1
        batch.results.append(IngestionResult(provider_message_id="msg-2", email_id=uuid.uuid4()))
        assert batch.ingested == 2
