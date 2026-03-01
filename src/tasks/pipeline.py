"""Celery pipeline: 5 tasks + run_pipeline orchestration.

Architecture:
  - Each task calls its service, commits independently (D13).
  - Each task enqueues the next task on success (no Celery ``link``/``chain``).
  - ``route_task`` bifurcates: enqueues ``crm_sync_task`` (if was_routed),
    which then enqueues ``draft_task`` on success.
  - ``run_pipeline`` is a plain Python function (NOT a Celery task).

Exception strategy (D7/D8):
  - Top-level ``except Exception``: ONLY place bare except permitted.
  - ``LLMRateLimitError``/``CRMRateLimitError``: retry with backoff.
  - ``CRMAuthError``: no retry (credentials invalid).
  - Local computation (flag eval, chain decision): no try/except.

PII (Sec 11.4): Only ``email_id`` and ``account_id`` in log statements.
"""

from __future__ import annotations

import asyncio
import uuid

import structlog

from src.tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)


def run_pipeline(email_id: uuid.UUID) -> None:
    """Enqueue the classification task for a newly ingested email.

    Preconditions:
      - ``email_id`` references an email in SANITIZED state (post-ingestion).
      - Celery broker (Redis) is accessible.

    Guarantees:
      - Enqueues ``classify_task.delay(str(email_id))``.
      - Fire-and-forget — no return value.

    External state errors:
      - ``kombu.exceptions.OperationalError`` if broker unreachable — propagated
        to caller (scheduler job or ingest_task).

    Note: NOT a Celery task. Called from ``ingest_task`` after each email.
    """
    classify_task.delay(str(email_id))


# ---------------------------------------------------------------------------
# Task 1: ingest_task
# ---------------------------------------------------------------------------


@celery_app.task(name="ingest_task", bind=True)  # type: ignore[untyped-decorator]
def ingest_task(self: object, account_id: str, since_iso: str) -> None:
    """Ingest emails for an account and enqueue classification for each.

    Preconditions:
      - ``account_id`` is a non-empty string.
      - ``since_iso`` is an ISO 8601 datetime string.

    Guarantees:
      - Delegates to ``IngestionService.ingest_batch()``.
      - Enqueues ``classify_task`` for each successfully ingested email.
    """
    try:
        asyncio.run(_run_ingestion_pipeline(account_id, since_iso))
    except Exception as exc:
        logger.error(
            "ingest_task_unexpected_error",
            account_id=account_id,
            error=str(exc),
        )
        raise self.retry(exc=exc) from exc  # type: ignore[attr-defined]


async def _run_ingestion_pipeline(account_id: str, since_iso: str) -> None:
    """Async bridge for ingestion with chaining to classify_task."""
    from datetime import datetime

    from src.tasks.ingestion_task import _run_ingestion

    since = datetime.fromisoformat(since_iso)

    logger.info(
        "ingest_task_started",
        account_id=account_id,
        since=since_iso,
    )

    result = await _run_ingestion(account_id, since)

    logger.info(
        "ingest_task_complete",
        account_id=account_id,
        lock_acquired=result.lock_acquired,
        ingested=result.ingested,
        skipped=result.skipped,
        failed=result.failed,
    )

    # Chain: enqueue classify for each successfully ingested email
    for individual in result.results:
        if individual.is_ingested and individual.email_id is not None:
            classify_task.delay(str(individual.email_id))


# ---------------------------------------------------------------------------
# Task 2: classify_task
# ---------------------------------------------------------------------------


@celery_app.task(name="classify_task", bind=True)  # type: ignore[untyped-decorator]
def classify_task(self: object, email_id: str) -> None:
    """Classify an email and enqueue routing on success.

    Preconditions:
      - ``email_id`` is a valid UUID string.
      - Email exists in DB in SANITIZED state.

    Guarantees:
      - On success: email -> CLASSIFIED, enqueues ``route_task``.
      - On ``LLMRateLimitError``: task retries with countdown.
      - On other exceptions: task retries with default backoff.
    """
    asyncio.run(_run_classification(self, email_id))


async def _run_classification(task: object, email_id_str: str) -> None:
    """Async bridge: load email, classify, chain to route_task."""
    from sqlalchemy import select

    from src.adapters.llm.exceptions import LLMRateLimitError
    from src.adapters.llm.litellm_adapter import LiteLLMAdapter
    from src.adapters.llm.schemas import LLMConfig
    from src.core.config import get_settings
    from src.core.database import AsyncSessionLocal
    from src.models.email import Email
    from src.services.classification import ClassificationService

    settings = get_settings()
    email_id = uuid.UUID(email_id_str)

    llm_config = LLMConfig(
        classify_model=settings.llm_model_classify,
        draft_model=settings.llm_model_draft,
        fallback_model=settings.llm_fallback_model,
        api_key=settings.openai_api_key or None,
        base_url=settings.llm_base_url or None,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    llm_adapter = LiteLLMAdapter(config=llm_config)
    service = ClassificationService(llm_adapter=llm_adapter, settings=settings)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Email).where(Email.id == email_id))
        email = result.scalar_one_or_none()

        if email is None:
            logger.error("classify_task_email_not_found", email_id=email_id_str)
            return

        try:
            classification = await service.classify_email(email_id, db)
            logger.info(
                "classify_task_complete",
                email_id=email_id_str,
                action=classification.action_slug,
                confidence=classification.confidence,
            )
            # Chain: enqueue routing
            route_task.delay(email_id_str)
        except LLMRateLimitError as exc:
            countdown = exc.retry_after_seconds or settings.celery_backoff_base
            logger.warning(
                "classify_task_rate_limited_retry",
                email_id=email_id_str,
                countdown=countdown,
            )
            raise task.retry(exc=exc, countdown=countdown) from exc  # type: ignore[attr-defined]
        except Exception as exc:
            logger.error(
                "classify_task_unexpected_error",
                email_id=email_id_str,
                error=str(exc),
            )
            raise task.retry(exc=exc) from exc  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Task 3: route_task
# ---------------------------------------------------------------------------


@celery_app.task(name="route_task", bind=True)  # type: ignore[untyped-decorator]
def route_task(self: object, email_id: str) -> None:
    """Route a classified email and conditionally enqueue CRM sync.

    Preconditions:
      - ``email_id`` is a valid UUID string.
      - Email exists in DB in CLASSIFIED state.

    Guarantees:
      - On success: email -> ROUTED, enqueues ``pipeline_crm_sync_task``
        if ``was_routed`` is True.
      - On exception: task retries.
    """
    asyncio.run(_run_routing(self, email_id))


async def _run_routing(task: object, email_id_str: str) -> None:
    """Async bridge: load email, route, chain to crm_sync_task."""
    from src.adapters.channel.base import ChannelAdapter
    from src.adapters.channel.schemas import ChannelCredentials
    from src.adapters.channel.slack import SlackAdapter
    from src.core.config import get_settings
    from src.core.database import AsyncSessionLocal
    from src.services.routing import RoutingService

    settings = get_settings()
    email_id = uuid.UUID(email_id_str)

    # Build channel adapters
    channel_adapters: dict[str, ChannelAdapter] = {}
    if settings.slack_bot_token:
        slack_adapter = SlackAdapter()
        await slack_adapter.connect(ChannelCredentials(bot_token=settings.slack_bot_token))
        channel_adapters["slack"] = slack_adapter

    service = RoutingService(channel_adapters=channel_adapters, settings=settings)

    async with AsyncSessionLocal() as db:
        try:
            routing_result = await service.route(email_id, db)
            logger.info(
                "route_task_complete",
                email_id=email_id_str,
                was_routed=routing_result.was_routed,
                actions_dispatched=routing_result.actions_dispatched,
            )
            # Bifurcation: enqueue CRM sync if routing was successful
            if routing_result.was_routed:
                pipeline_crm_sync_task.delay(email_id_str)
        except Exception as exc:
            logger.error(
                "route_task_unexpected_error",
                email_id=email_id_str,
                error=str(exc),
            )
            raise task.retry(exc=exc) from exc  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Task 4: pipeline_crm_sync_task
# ---------------------------------------------------------------------------


@celery_app.task(name="pipeline_crm_sync_task", bind=True)  # type: ignore[untyped-decorator]
def pipeline_crm_sync_task(self: object, email_id: str) -> None:
    """CRM sync with chaining to draft generation on success.

    Delegates to existing ``_run_crm_sync`` implementation, then
    enqueues ``pipeline_draft_task`` if email reached CRM_SYNCED state.

    Preconditions:
      - ``email_id`` is a valid UUID string.
      - Email exists in DB in ROUTED state.

    Guarantees:
      - On success: email -> CRM_SYNCED, enqueues ``pipeline_draft_task``.
      - On ``CRMAuthError``: email -> CRM_SYNC_FAILED (no retry, no chain).
      - On ``CRMRateLimitError``: task retries with countdown.
      - On other exceptions: task retries.
    """
    asyncio.run(_run_crm_sync_with_chain(self, email_id))


async def _run_crm_sync_with_chain(task: object, email_id_str: str) -> None:
    """Run CRM sync and chain to draft on success."""
    from sqlalchemy import select

    from src.core.database import AsyncSessionLocal
    from src.models.email import Email, EmailState
    from src.tasks.crm_sync_task import _run_crm_sync

    # Delegate to existing CRM sync implementation
    await _run_crm_sync(task, email_id_str)

    # Check if CRM sync succeeded — chain to draft if so
    email_id = uuid.UUID(email_id_str)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Email).where(Email.id == email_id))
        email = result.scalar_one_or_none()

        if email is not None and email.state == EmailState.CRM_SYNCED:
            pipeline_draft_task.delay(email_id_str)


# ---------------------------------------------------------------------------
# Task 5: pipeline_draft_task
# ---------------------------------------------------------------------------


@celery_app.task(name="pipeline_draft_task", bind=True)  # type: ignore[untyped-decorator]
def pipeline_draft_task(self: object, email_id: str) -> None:
    """Draft generation — terminal task in the pipeline.

    Delegates to existing ``_run_draft_generation`` implementation.

    Preconditions:
      - ``email_id`` is a valid UUID string.
      - Email exists in DB in CRM_SYNCED state.

    Guarantees:
      - On success: email -> DRAFT_GENERATED.
      - On ``LLMRateLimitError``: task retries with countdown.
      - On other exceptions: task retries.
    """
    from src.tasks.draft_generation_task import _run_draft_generation

    asyncio.run(_run_draft_generation(self, email_id))
