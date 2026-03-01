"""Celery task wrapper for email ingestion.

The task is the Celery entry point — it creates the IngestionService with
proper dependencies and delegates to ``ingest_batch()``. The service is
fully async; the task bridges sync Celery → async service via ``asyncio.run()``.

try-except D7: Top-level Celery handler is the ONLY place bare ``except
Exception`` is permitted, to ensure task retry on unexpected failures.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import structlog

from src.services.schemas.ingestion import IngestionBatchResult

logger = structlog.get_logger(__name__)


def ingest_emails_task(account_id: str, since_iso: str) -> None:
    """Celery-callable entry point for email ingestion.

    Preconditions:
      - ``account_id`` is a non-empty string identifying the email account.
      - ``since_iso`` is an ISO 8601 datetime string (timezone-aware).

    Guarantees:
      - Delegates to ``IngestionService.ingest_batch()``.
      - Logs batch result summary.

    Note: This is a plain function, not a Celery task decorator. Block 12
    (Celery Pipeline) will register it with the Celery app and add retry
    logic. For now it can be called directly or registered later.
    """
    since = datetime.fromisoformat(since_iso)

    logger.info(
        "ingestion_task_started",
        account_id=account_id,
        since=since_iso,
    )

    result = asyncio.run(_run_ingestion(account_id, since))

    logger.info(
        "ingestion_task_complete",
        account_id=account_id,
        lock_acquired=result.lock_acquired,
        ingested=result.ingested,
        skipped=result.skipped,
        failed=result.failed,
    )


async def _run_ingestion(
    account_id: str,
    since: datetime,
) -> IngestionBatchResult:
    """Async bridge: construct dependencies and run ingestion.

    This is intentionally minimal — Block 12 will formalize dependency
    injection for Celery tasks. For now, imports are deferred to avoid
    circular imports at module level.
    """
    from redis.asyncio import Redis

    from src.core.config import get_settings
    from src.core.database import AsyncSessionLocal
    from src.services.ingestion import IngestionService

    settings = get_settings()

    redis = Redis.from_url(settings.redis_url)
    try:
        async with AsyncSessionLocal() as session:
            # TODO(B12): adapter instantiation will come from account config
            # For now, this function is tested with mocked IngestionService
            service = IngestionService(
                adapter=None,  # type: ignore[arg-type]
                session=session,
                redis=redis,
                settings=settings,
            )
            return await service.ingest_batch(account_id, since=since)
    finally:
        await redis.aclose()
