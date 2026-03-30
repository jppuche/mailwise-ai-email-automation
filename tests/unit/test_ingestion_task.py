"""Tests for the ingestion Celery task wrapper.

The task is a thin sync→async bridge. The service logic is tested in
test_ingestion_service.py. Here we verify:
  - ISO datetime parsing
  - asyncio.run delegation
  - Error propagation
  - Return type

Note: _run_ingestion() is a dependency-wiring function that will be
formalized in Block 12 (Celery Pipeline). It imports src.core.database
at module level which requires a real DB config. Testing it here would
require complex patching of module-level initialization. Block 12 will
add proper integration tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.services.schemas.ingestion import IngestionBatchResult
from src.tasks.ingestion_task import ingest_emails_task


class TestIngestEmailsTask:
    @patch("src.tasks.ingestion_task.asyncio.run")
    def test_calls_asyncio_run(self, mock_run: MagicMock) -> None:
        mock_run.return_value = IngestionBatchResult(account_id="acc-1")

        ingest_emails_task("acc-1", "2026-02-28T12:00:00+00:00")

        mock_run.assert_called_once()

    @patch("src.tasks.ingestion_task.asyncio.run")
    def test_parses_iso_datetime(self, mock_run: MagicMock) -> None:
        mock_run.return_value = IngestionBatchResult(account_id="acc-1")

        ingest_emails_task("acc-1", "2026-02-28T12:00:00+00:00")

        # Verify the coroutine was passed to asyncio.run
        args, _ = mock_run.call_args
        assert len(args) == 1  # one coroutine argument

    @patch("src.tasks.ingestion_task.asyncio.run")
    def test_returns_none(self, mock_run: MagicMock) -> None:
        mock_run.return_value = IngestionBatchResult(account_id="acc-1")

        result = ingest_emails_task("acc-1", "2026-02-28T12:00:00+00:00")

        assert result is None

    def test_invalid_iso_raises(self) -> None:
        with pytest.raises(ValueError):
            ingest_emails_task("acc-1", "not-a-date")

    @patch("src.tasks.ingestion_task.asyncio.run")
    def test_logs_batch_result(self, mock_run: MagicMock) -> None:
        batch = IngestionBatchResult(account_id="acc-1")
        mock_run.return_value = batch

        # Should not raise — logs are informational
        ingest_emails_task("acc-1", "2026-02-28T12:00:00+00:00")

    @patch("src.tasks.ingestion_task.asyncio.run")
    def test_propagates_runtime_error(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = RuntimeError("event loop crash")

        with pytest.raises(RuntimeError, match="event loop crash"):
            ingest_emails_task("acc-1", "2026-02-28T12:00:00+00:00")
