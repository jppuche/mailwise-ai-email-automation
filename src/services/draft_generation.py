"""Draft generation service — orchestrates LLM draft creation, DB persist, optional Gmail push.

Precondition: email.state MUST be CRM_SYNCED. Uses email.transition_to(), never direct assignment.

contract-docstrings:
  Invariants: LLM adapter and email adapter must be initialized before generate().
  Guarantees: generate() always returns a DraftResult. Draft is committed (D13) before
    Gmail push attempt. Gmail push failure → DRAFT_GENERATED (NOT DRAFT_FAILED).
  Errors raised: LLMRateLimitError (re-raised to Celery task for retry).
  Errors silenced: LLMConnectionError, LLMTimeoutError → DRAFT_FAILED result.
    EmailAdapterError → logged warning, pushed_to_provider stays False.
    SQLAlchemyError on Draft persist → DRAFT_FAILED result.
  External state: PostgreSQL (Draft + Email), LLM adapter, Gmail adapter.

try-except D7/D8:
  External-state ops (LLM, Gmail, DB): structured try/except with specific types.
  Local computation (DraftContextBuilder): zero try/except (delegated to draft_context.py).

pre-mortem:
  Cat 6: Draft committed independently (D13) — Gmail push failure does not lose draft.
  Cat 8: All defaults from DraftGenerationConfig (sourced from Settings env vars).
"""

from __future__ import annotations

import asyncio
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.email.base import EmailAdapter
from src.adapters.llm.base import LLMAdapter
from src.adapters.llm.exceptions import (
    LLMConnectionError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from src.adapters.llm.schemas import DraftOptions
from src.models.crm_sync import CRMSyncRecord, CRMSyncStatus
from src.models.draft import Draft
from src.models.email import Email, EmailState
from src.services.draft_context import DraftContextBuilder
from src.services.schemas.draft import (
    DraftGenerationConfig,
    DraftRequest,
    DraftResult,
)

logger = structlog.get_logger(__name__)


class DraftGenerationService:
    """Orchestrates draft generation: context assembly → LLM call → persist → optional push.

    Invariants:
      - ``llm_adapter`` must be initialized before ``generate()`` is called.
      - ``email_adapter`` must be initialized if ``push_to_gmail`` is True.
      - ``config`` provides all Cat 8 configurable defaults.

    Guarantees:
      - ``generate()`` always returns a ``DraftResult``.
      - Draft is committed (D13) before Gmail push attempt.
      - Gmail push failure → ``DRAFT_GENERATED`` (not ``DRAFT_FAILED``).

    Errors raised:
      - ``LLMRateLimitError``: re-raised to Celery task (retry with backoff).

    Errors silenced:
      - ``LLMConnectionError``, ``LLMTimeoutError``: → DRAFT_FAILED result.
      - ``EmailAdapterError``: logged warning, ``pushed_to_provider`` stays False.
      - ``SQLAlchemyError`` on Draft persist: → DRAFT_FAILED result.
    """

    def __init__(
        self,
        *,
        llm_adapter: LLMAdapter,
        email_adapter: EmailAdapter,
        config: DraftGenerationConfig,
    ) -> None:
        self._llm_adapter = llm_adapter
        self._email_adapter = email_adapter
        self._config = config
        self._context_builder = DraftContextBuilder()

    async def generate(
        self,
        request: DraftRequest,
        db: AsyncSession,
    ) -> DraftResult:
        """Generate a draft reply for the given email.

        Preconditions:
          - Email with ``request.email_id`` exists in DB with state ``CRM_SYNCED``.
          - ``request.email_content.body_snippet`` is pre-truncated.

        Guarantees:
          - Returns ``DraftResult`` with appropriate status.
          - Draft persisted in DB before any Gmail push (D13).
          - ``LLMRateLimitError`` is the ONLY exception re-raised.

        External state: PostgreSQL, LLM adapter, Gmail adapter.
        """
        email_id = request.email_id

        # Step 1: Load CRM record from DB (optional, for context) — external state (D7)
        crm_record = await self._load_crm_record(email_id, db)

        # Step 2: Load template from DB if template_id set (placeholder for B14)
        template_content: str | None = None
        # B14 will implement template loading — for now, always None

        # Step 3: Build context — local computation (D8), delegated to DraftContextBuilder
        context = self._context_builder.build(
            request=request,
            crm_record=crm_record,
            template_content=template_content,
            org_context=self._config.org_context,
        )

        # Step 4: Build LLM prompt — local computation (D8)
        prompt = self._context_builder.build_llm_prompt(context)
        system_prompt = self._config.org_context.system_prompt

        # Step 5: Call LLM — external state (D7)
        try:
            draft_text = await self._llm_adapter.generate_draft(
                prompt=prompt,
                system_prompt=system_prompt,
                options=DraftOptions(),
            )
        except LLMRateLimitError:
            # Re-raise to Celery task for retry — email stays CRM_SYNCED
            raise
        except (LLMConnectionError, LLMTimeoutError) as exc:
            logger.error(
                "draft_llm_call_failed",
                email_id=str(email_id),
                error=str(exc),
            )
            return await self._handle_failure(
                email_id=email_id,
                db=db,
                error_detail=str(exc),
            )

        # Step 6: Create Draft ORM and persist — external state (D7)
        draft_id = uuid.uuid4()
        draft = Draft(
            id=draft_id,
            email_id=email_id,
            content=draft_text.content,
        )

        try:
            db.add(draft)
            await db.flush()
            # Step 7: COMMIT (D13) — draft persists before push
            await db.commit()
        except SQLAlchemyError as exc:
            await db.rollback()
            logger.error(
                "draft_persist_failed",
                email_id=str(email_id),
                error=str(exc),
            )
            return await self._handle_failure(
                email_id=email_id,
                db=db,
                error_detail=f"DB persist failed: {exc}",
            )

        # Step 8: Transition email state — external state (D7)
        try:
            result_obj = await db.execute(
                select(Email).where(Email.id == email_id)
            )
            email_orm = result_obj.scalar_one_or_none()
            if email_orm is not None:
                email_orm.transition_to(EmailState.DRAFT_GENERATED)
                await db.commit()
        except SQLAlchemyError as exc:
            logger.warning(
                "draft_state_transition_failed",
                email_id=str(email_id),
                error=str(exc),
            )
            # Draft already committed — state transition failure is non-fatal

        # Step 9: Optional Gmail push — external state (D7)
        gmail_draft_id: str | None = None
        pushed_to_provider = False
        push_failed = False
        should_push = request.push_to_gmail or self._config.push_to_gmail

        if should_push:
            gmail_draft_id, pushed_to_provider, push_failed = (
                await self._push_to_gmail(request, draft_text.content)
            )

        # Step 10: Return result — local computation (D8)
        status = "generated"
        if push_failed:
            status = "generated_push_failed"

        logger.info(
            "draft_generation_complete",
            email_id=str(email_id),
            draft_id=str(draft_id),
            model_used=draft_text.model_used,
            status=status,
        )

        return DraftResult(
            email_id=email_id,
            draft_id=draft_id,
            gmail_draft_id=gmail_draft_id,
            status=status,
            model_used=draft_text.model_used,
            fallback_applied=draft_text.fallback_applied,
        )

    async def _load_crm_record(
        self,
        email_id: uuid.UUID,
        db: AsyncSession,
    ) -> CRMSyncRecord | None:
        """Load the most recent SYNCED CRMSyncRecord for this email.

        External state (D7): SQLAlchemyError caught, returns None.
        """
        try:
            result = await db.execute(
                select(CRMSyncRecord)
                .where(CRMSyncRecord.email_id == email_id)
                .where(CRMSyncRecord.status == CRMSyncStatus.SYNCED)
                .order_by(CRMSyncRecord.synced_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            logger.warning(
                "draft_crm_record_load_failed",
                email_id=str(email_id),
                error=str(exc),
            )
            return None

    async def _handle_failure(
        self,
        *,
        email_id: uuid.UUID,
        db: AsyncSession,
        error_detail: str,
    ) -> DraftResult:
        """Transition email to DRAFT_FAILED and return a failed DraftResult.

        External state (D7): SQLAlchemyError on state transition logged, not re-raised.
        """
        try:
            result = await db.execute(
                select(Email).where(Email.id == email_id)
            )
            email_orm = result.scalar_one_or_none()
            if email_orm is not None:
                email_orm.transition_to(EmailState.DRAFT_FAILED)
                await db.commit()
        except SQLAlchemyError as exc:
            logger.warning(
                "draft_failure_state_transition_failed",
                email_id=str(email_id),
                error=str(exc),
            )

        return DraftResult(
            email_id=email_id,
            status="failed",
            error_detail=error_detail,
        )

    async def _push_to_gmail(
        self,
        request: DraftRequest,
        content: str,
    ) -> tuple[str | None, bool, bool]:
        """Push draft to Gmail via email adapter.

        External state (D7): EmailAdapterError caught, logged, returns failure tuple.
        Gmail push failure → DRAFT_GENERATED (NOT DRAFT_FAILED) per SCRATCHPAD B11.

        Returns (gmail_draft_id, pushed_to_provider, push_failed).
        """
        from src.adapters.email.exceptions import EmailAdapterError

        try:
            draft_id = await asyncio.to_thread(
                self._email_adapter.create_draft,
                to=request.email_content.sender_email,
                subject=f"Re: {request.email_content.subject}",
                body=content,
            )
            logger.info(
                "draft_pushed_to_gmail",
                email_id=str(request.email_id),
                gmail_draft_id=str(draft_id),
            )
            return str(draft_id), True, False
        except EmailAdapterError as exc:
            logger.warning(
                "draft_gmail_push_failed",
                email_id=str(request.email_id),
                error=str(exc),
            )
            return None, False, True
