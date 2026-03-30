"""Celery task wrapper for draft generation.

Bridges sync Celery context -> async DraftGenerationService via asyncio.run().
Manages retry/no-retry decisions based on exception type.

Top-level except Exception is the ONLY place bare except is permitted --
Celery task handler pattern.
"""

from __future__ import annotations

import asyncio

import structlog

logger = structlog.get_logger(__name__)


def draft_generation_task(self: object, email_id: str) -> None:
    """Celery-callable entry point for draft generation.

    Preconditions:
      - email_id is a valid UUID string.
      - Email exists in DB in CRM_SYNCED state.

    Guarantees:
      - On success: email -> DRAFT_GENERATED.
      - On LLMRateLimitError: task retries with countdown.
      - On other exceptions: task retries with default backoff.

    Note: Plain function stub -- the Celery pipeline registers this with the task decorator.
    """
    asyncio.run(_run_draft_generation(self, email_id))


async def _run_draft_generation(task: object, email_id_str: str) -> None:
    """Async bridge: load email, build request, call service, manage state.

    Preconditions:
      - email_id_str is a valid UUID string parseable by uuid.UUID().
      - Settings contain valid LLM credentials and draft config.

    Guarantees:
      - Email not found: logs error, returns without raising.
      - LLMRateLimitError: raises task.retry() with countdown.
      - Other exceptions: raises task.retry() with default backoff.

    Errors silenced:
      - None — all exceptions either result in state change or are re-raised.

    Privacy (Sec 6.5):
      - body_plain and body_html are never logged.
      - body_snippet is truncated to max_body_length before building request.
      - Logger never logs subject, sender_email, body_snippet.

    Note: Deferred imports avoid circular imports at module level.
    """
    import uuid

    from sqlalchemy import select

    from src.adapters.email.gmail import GmailAdapter
    from src.adapters.llm.exceptions import LLMRateLimitError
    from src.adapters.llm.litellm_adapter import LiteLLMAdapter
    from src.adapters.llm.schemas import LLMConfig
    from src.core.config import get_settings
    from src.core.database import AsyncSessionLocal
    from src.models.email import Email
    from src.services.draft_generation import DraftGenerationService
    from src.services.schemas.draft import (
        ClassificationContext,
        DraftGenerationConfig,
        DraftRequest,
        EmailContent,
        OrgContext,
    )

    settings = get_settings()
    email_id = uuid.UUID(email_id_str)

    org_context = OrgContext(
        system_prompt=settings.draft_org_system_prompt,
        tone=settings.draft_org_tone,
        signature=settings.draft_org_signature or None,
        prohibited_language=[
            s.strip() for s in settings.draft_org_prohibited_language.split(",") if s.strip()
        ],
    )

    config = DraftGenerationConfig(
        push_to_gmail=settings.draft_push_to_gmail,
        org_context=org_context,
        retry_max=settings.draft_generation_retry_max,
    )

    llm_config = LLMConfig(
        classify_model=settings.llm_model_classify,
        draft_model=settings.llm_model_draft,
        fallback_model=settings.llm_fallback_model,
        api_key=settings.openai_api_key or None,
        base_url=settings.llm_base_url or None,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    llm_adapter = LiteLLMAdapter(config=llm_config)
    email_adapter = GmailAdapter()

    service = DraftGenerationService(
        llm_adapter=llm_adapter,
        email_adapter=email_adapter,
        config=config,
    )

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Email).where(Email.id == email_id))
        email = result.scalar_one_or_none()

        if email is None:
            logger.error("draft_task_email_not_found", email_id=email_id_str)
            return

        # Build request — privacy: body_snippet truncated, no body_plain/body_html
        body_snippet = (email.body_plain or "")[: settings.max_body_length]
        request = DraftRequest(
            email_id=email.id,
            email_content=EmailContent(
                sender_email=email.sender_email,
                sender_name=email.sender_name,
                subject=email.subject,
                body_snippet=body_snippet,
                received_at=email.date.isoformat() if email.date else "",
            ),
            classification=ClassificationContext(
                action="",  # Classification result will be loaded from DB
                type="",
                confidence="low",
            ),
            push_to_gmail=config.push_to_gmail,
        )

        try:
            await service.generate(request, db)
            logger.info(
                "draft_task_complete",
                email_id=email_id_str,
            )
        except LLMRateLimitError as exc:
            countdown = exc.retry_after_seconds or 60
            logger.warning(
                "draft_task_rate_limited_retry",
                email_id=email_id_str,
                countdown=countdown,
            )
            raise task.retry(exc=exc, countdown=countdown) from exc  # type: ignore[attr-defined]
        except Exception as exc:
            # Top-level handler -- only permitted bare except in Celery tasks.
            logger.error(
                "draft_task_unexpected_error",
                email_id=email_id_str,
                error=str(exc),
            )
            raise task.retry(exc=exc) from exc  # type: ignore[attr-defined]
