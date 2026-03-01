"""Celery task wrapper for CRM synchronization.

Bridges sync Celery context -> async CRMSyncService via asyncio.run().
Manages retry/no-retry decisions based on exception type.

try-except D7: Top-level except Exception is the ONLY place bare
except is permitted -- Celery task handler pattern.
"""

from __future__ import annotations

import asyncio

import structlog

logger = structlog.get_logger(__name__)


def crm_sync_task(self: object, email_id: str) -> None:
    """Celery-callable entry point for CRM sync.

    Preconditions:
      - email_id is a valid UUID string.
      - Email exists in DB in ROUTED or CRM_SYNC_FAILED state.

    Guarantees:
      - On success: email -> CRM_SYNCED.
      - On CRMAuthError: email -> CRM_SYNC_FAILED (no retry).
      - On CRMRateLimitError: task retries with countdown.
      - On other exceptions: task retries with default backoff.

    Note: Plain function stub -- Block 12 registers with Celery decorator.
    """
    asyncio.run(_run_crm_sync(self, email_id))


async def _run_crm_sync(task: object, email_id_str: str) -> None:
    """Async bridge: load email, build request, call service, manage state.

    Preconditions:
      - email_id_str is a valid UUID string parseable by uuid.UUID().
      - Settings contain valid HubSpot credentials and CRM sync config.

    Guarantees:
      - Email not found: logs error, returns without raising.
      - CRMAuthError: transitions email to CRM_SYNC_FAILED, commits, returns.
      - CRMRateLimitError: raises task.retry() with countdown from header or
        backoff_base_seconds.
      - Other exceptions: raises task.retry() with default backoff.

    Errors silenced:
      - None — all exceptions either result in state change or are re-raised.

    Privacy (Sec 6.5):
      - body_plain and body_html are never read or included in CRMSyncRequest.
      - snippet is truncated to activity_snippet_length before building request.
      - Logger never logs subject, sender_email, or snippet.

    Note: Deferred imports avoid circular imports at module level.
    Block 12 will formalize dependency injection for Celery tasks.
    """
    import uuid

    from sqlalchemy import select

    from src.adapters.crm.exceptions import CRMAuthError, CRMRateLimitError
    from src.adapters.crm.hubspot import HubSpotAdapter
    from src.adapters.crm.schemas import CRMCredentials
    from src.core.config import get_settings
    from src.core.database import AsyncSessionLocal
    from src.models.email import Email, EmailState
    from src.services.crm_sync import CRMSyncService
    from src.services.schemas.crm_sync import CRMSyncConfig, CRMSyncRequest

    settings = get_settings()
    email_id = uuid.UUID(email_id_str)

    config = CRMSyncConfig(
        auto_create_contacts=settings.hubspot_auto_create_contacts,
        activity_snippet_length=settings.hubspot_activity_snippet_length,
        retry_max=settings.crm_sync_retry_max,
        backoff_base_seconds=settings.crm_sync_backoff_base_seconds,
    )

    adapter = HubSpotAdapter()
    await adapter.connect(CRMCredentials(access_token=settings.hubspot_access_token))

    service = CRMSyncService(crm_adapter=adapter, config=config)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Email).where(Email.id == email_id))
        email = result.scalar_one_or_none()

        if email is None:
            logger.error("crm_sync_task_email_not_found", email_id=email_id_str)
            return

        # Build request -- privacy: no body_plain/body_html fields in CRMSyncRequest
        truncated_snippet = (email.snippet or "")[: settings.hubspot_activity_snippet_length]
        request = CRMSyncRequest(
            email_id=email.id,
            sender_email=email.sender_email,
            sender_name=email.sender_name,
            subject=email.subject,
            snippet=truncated_snippet,
            classification_action="",  # B12 will load from ClassificationResult
            classification_type="",
            received_at=email.date,
        )

        try:
            sync_result = await service.sync(request, db)
            if sync_result.overall_success:
                email.transition_to(EmailState.CRM_SYNCED)
            else:
                email.transition_to(EmailState.CRM_SYNC_FAILED)
            await db.commit()
            logger.info(
                "crm_sync_task_complete",
                email_id=email_id_str,
                overall_success=sync_result.overall_success,
                contact_id=sync_result.contact_id,
            )
        except CRMAuthError as exc:
            # No retry -- credentials invalid until operator renews token.
            email.transition_to(EmailState.CRM_SYNC_FAILED)
            await db.commit()
            logger.error(
                "crm_sync_task_auth_error_no_retry",
                email_id=email_id_str,
                error=str(exc),
            )
        except CRMRateLimitError as exc:
            countdown = exc.retry_after_seconds or config.backoff_base_seconds
            logger.warning(
                "crm_sync_task_rate_limited_retry",
                email_id=email_id_str,
                countdown=countdown,
            )
            raise task.retry(exc=exc, countdown=countdown) from exc  # type: ignore[attr-defined]
        except Exception as exc:
            # Top-level handler -- only permitted bare except per D7.
            logger.error(
                "crm_sync_task_unexpected_error",
                email_id=email_id_str,
                error=str(exc),
            )
            raise task.retry(exc=exc) from exc  # type: ignore[attr-defined]
