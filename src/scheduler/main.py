"""APScheduler entry point for the dedicated scheduler container.

Runs as a standalone process — no FastAPI, no API imports.
Configures an ``AsyncIOScheduler`` with an interval trigger for
``poll_email_accounts_job``.

Fail-fast assertion: ``lock_ttl >= poll_interval`` at startup (Cat 8).
"""

from __future__ import annotations

import asyncio

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.core.config import get_settings
from src.scheduler.jobs import poll_email_accounts_job

logger = structlog.get_logger(__name__)


async def main() -> None:
    """Scheduler entry point — configure and start APScheduler.

    Preconditions:
      - Settings loaded from env vars.
      - ``pipeline_scheduler_lock_ttl_seconds >= polling_interval_seconds``
        (fail-fast assertion).

    Guarantees:
      - ``poll_email_accounts_job`` runs at ``polling_interval_seconds`` intervals.
      - Scheduler runs until interrupted (SIGINT/SIGTERM).

    Note: No imports from ``src.api`` — scheduler is a separate container.
    """
    settings = get_settings()

    # Cat 8 fail-fast: lock TTL must cover the full poll interval
    assert settings.pipeline_scheduler_lock_ttl_seconds >= settings.polling_interval_seconds, (
        f"Lock TTL ({settings.pipeline_scheduler_lock_ttl_seconds}s) must be >= "
        f"poll interval ({settings.polling_interval_seconds}s)"
    )

    from datetime import UTC

    scheduler = AsyncIOScheduler(timezone=UTC)
    scheduler.add_job(
        poll_email_accounts_job,
        IntervalTrigger(seconds=settings.polling_interval_seconds),
        id="poll_email_accounts",
        replace_existing=True,
    )

    logger.info(
        "scheduler_starting",
        poll_interval_seconds=settings.polling_interval_seconds,
        lock_ttl_seconds=settings.pipeline_scheduler_lock_ttl_seconds,
    )

    scheduler.start()

    # Keep the event loop running
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("scheduler_shutting_down")
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
