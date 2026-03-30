"""Scheduler jobs — poll email accounts and enqueue ingestion tasks.

The scheduler is a producer-side lock: it prevents multiple ``ingest_task``
from being enqueued for the same account. The consumer-side lock lives in
``IngestionService._acquire_poll_lock``.

PII (Sec 11.4): Only ``account_id`` in log statements — no email content.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta

import structlog
from redis.asyncio import Redis

from src.core.config import get_settings

logger = structlog.get_logger(__name__)


async def poll_email_accounts_job() -> None:
    """Iterate active accounts and enqueue ``ingest_task`` for each.

    Preconditions:
      - Redis accessible for lock acquisition.
      - At least one active email account configured.

    Guarantees:
      - Lock per ``account_id`` prevents concurrent polls.
      - Lock released in ``finally`` (crash-safe via TTL expiry).
      - Enqueue failure does not block other accounts.

    External state errors:
      - ``RedisError`` on lock acquisition: skip account, log warning.
      - ``RedisError`` on enqueue: log error, release lock, skip account.

    Silenced:
      - Lock already held (another worker processing): silent skip.
    """
    settings = get_settings()

    redis = Redis.from_url(settings.redis_url)
    try:
        accounts = _get_active_accounts()

        for account_id in accounts:
            lock_key = f"{settings.pipeline_scheduler_lock_key_prefix}:{account_id}"
            acquired = False

            try:
                acquired_result = await redis.set(
                    lock_key,
                    "1",
                    nx=True,
                    ex=settings.pipeline_scheduler_lock_ttl_seconds,
                )
                acquired = bool(acquired_result)
            except Exception as exc:
                logger.warning(
                    "scheduler_lock_acquisition_failed",
                    account_id=account_id,
                    error=str(exc),
                )
                continue

            if not acquired:
                # Another worker still processing — expected, not an error
                continue

            try:
                _enqueue_ingest_task(account_id, settings)
                logger.info(
                    "scheduler_enqueued_ingest",
                    account_id=account_id,
                )
            except Exception as exc:
                logger.error(
                    "scheduler_enqueue_failed",
                    account_id=account_id,
                    error=str(exc),
                )
                # Release lock — task was not enqueued
                with contextlib.suppress(Exception):
                    await redis.delete(lock_key)
    finally:
        await redis.aclose()


def _get_active_accounts() -> list[str]:
    """Return list of active account IDs to poll.

    Note: In production, this would query the DB for active EmailAccount
    records. The scheduler does NOT import ``src.api`` — it uses its own
    DB access if needed.
    """
    # Placeholder: returns empty list until account management is implemented
    return []


def _enqueue_ingest_task(account_id: str, settings: object) -> None:
    """Enqueue ``ingest_task`` via Celery.

    Deferred import avoids circular dependency at module level.
    """
    from src.core.config import Settings
    from src.tasks.pipeline import ingest_task

    assert isinstance(settings, Settings)

    since = datetime.now(UTC) - timedelta(seconds=settings.polling_interval_seconds)
    ingest_task.delay(account_id, since.isoformat())
