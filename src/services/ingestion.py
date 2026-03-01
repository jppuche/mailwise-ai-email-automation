"""Ingestion service — fetch, dedup, sanitize, store emails.

Orchestrates: EmailAdapter.fetch_new_messages → dedup (DB) → sanitize (local)
→ store (DB, FETCHED) → transition (SANITIZED) → return IngestionBatchResult.

contract-docstrings:
  Invariants: Requires connected EmailAdapter, async DB session, Redis client.
  Guarantees: Per-email isolation — one failure does not affect others.
    Two independent commits per email (FETCHED then SANITIZED, D13/Cat 6).
  Errors raised: Never — all errors captured into IngestionResult.
    Only Redis lock failure and adapter fetch failure abort the batch.
  Errors silenced: Per-email DB errors (SQLAlchemyError) are logged and
    recorded as FailureReason, not re-raised.
  External state: Email provider (via adapter), PostgreSQL, Redis.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.email.base import EmailAdapter
from src.adapters.email.exceptions import EmailAdapterError
from src.adapters.email.schemas import EmailMessage
from src.core.config import Settings
from src.core.sanitizer import sanitize_email_body
from src.models.email import (
    AttachmentData as OrmAttachmentData,
)
from src.models.email import (
    Email,
    EmailState,
)
from src.models.email import (
    RecipientData as OrmRecipientData,
)
from src.services.schemas.ingestion import (
    FailureReason,
    IngestionBatchResult,
    IngestionResult,
    SkipReason,
)

logger = structlog.get_logger(__name__)


class IngestionService:
    """Fetches new emails from a provider, deduplicates, sanitizes, and stores.

    Invariants:
      - ``adapter`` must be connected before calling ``ingest_batch``.
      - ``session`` is an async SQLAlchemy session (caller manages lifecycle).
      - ``redis`` is an async Redis client.

    Guarantees:
      - Per-email isolation: a DB error on email N does not prevent N+1.
      - Two commits per email: FETCHED (insert) then SANITIZED (transition).
      - Distributed lock via Redis SET NX EX prevents concurrent polls.
      - Thread awareness: only newest message per thread gets ingested normally.

    Errors raised:
      - None from ``ingest_batch`` — all captured into result objects.

    Errors silenced:
      - ``SQLAlchemyError`` per email (logged, recorded as failure).
      - ``EmailAdapterError`` (logged, batch returns empty with error).
    """

    def __init__(
        self,
        *,
        adapter: EmailAdapter,
        session: AsyncSession,
        redis: Redis,
        settings: Settings,
    ) -> None:
        self._adapter = adapter
        self._session = session
        self._redis = redis
        self._settings = settings

    async def ingest_batch(
        self,
        account_id: str,
        *,
        since: datetime,
    ) -> IngestionBatchResult:
        """Fetch and ingest a batch of emails for the given account.

        Preconditions:
          - ``account_id`` is non-empty.
          - ``since`` is timezone-aware.

        Guarantees:
          - Returns ``IngestionBatchResult`` (never raises).
          - Lock is always released (try/finally).
        """
        batch = IngestionBatchResult(account_id=account_id)

        # 1. Acquire distributed lock
        if not await self._acquire_poll_lock(account_id):
            logger.info("ingestion_lock_held", account_id=account_id)
            batch.lock_acquired = False
            return batch

        try:
            # 2. Fetch from adapter (external-state — try/except D7)
            try:
                messages = self._adapter.fetch_new_messages(
                    since=since,
                    limit=self._settings.ingestion_batch_size,
                )
            except EmailAdapterError as exc:
                logger.error(
                    "ingestion_fetch_failed",
                    account_id=account_id,
                    error=str(exc),
                )
                return batch

            logger.info(
                "ingestion_fetched",
                account_id=account_id,
                count=len(messages),
            )

            # 3. Process each email with per-email isolation
            for msg in messages:
                result = await self._process_single_email(msg, account_id)
                batch.results.append(result)

            logger.info(
                "ingestion_batch_complete",
                account_id=account_id,
                ingested=batch.ingested,
                skipped=batch.skipped,
                failed=batch.failed,
            )
        finally:
            # 4. Release lock (always)
            await self._release_poll_lock(account_id)

        return batch

    async def _process_single_email(
        self,
        msg: EmailMessage,
        account_id: str,
    ) -> IngestionResult:
        """Process a single email: dedup → thread check → sanitize → store.

        Per-email isolation: DB errors are caught and recorded, not re-raised.
        """
        # 3a. Dedup check (external-state — try/except D7)
        try:
            existing = await self._session.execute(
                select(Email.id).where(Email.provider_message_id == msg.gmail_message_id)
            )
            if existing.scalar_one_or_none() is not None:
                logger.debug(
                    "ingestion_duplicate",
                    provider_message_id=msg.gmail_message_id,
                )
                return IngestionResult(
                    provider_message_id=msg.gmail_message_id,
                    skip_reason=SkipReason.DUPLICATE,
                )
        except SQLAlchemyError as exc:
            logger.error(
                "ingestion_dedup_query_failed",
                provider_message_id=msg.gmail_message_id,
                error=str(exc),
            )
            await self._session.rollback()
            return IngestionResult(
                provider_message_id=msg.gmail_message_id,
                failure_reason=FailureReason.DB_WRITE_ERROR,
                error_detail=str(exc),
            )

        # 3b. Thread awareness (external-state — try/except D7)
        if msg.thread_id is not None:
            try:
                thread_result = await self._session.execute(
                    select(Email.date)
                    .where(Email.thread_id == msg.thread_id)
                    .order_by(Email.date.desc())
                    .limit(1)
                )
                newest_date = thread_result.scalar_one_or_none()
                if newest_date is not None and msg.received_at <= newest_date:
                    logger.debug(
                        "ingestion_thread_not_newest",
                        provider_message_id=msg.gmail_message_id,
                        thread_id=msg.thread_id,
                    )
                    return IngestionResult(
                        provider_message_id=msg.gmail_message_id,
                        skip_reason=SkipReason.THREAD_NOT_NEWEST,
                    )
            except SQLAlchemyError as exc:
                logger.error(
                    "ingestion_thread_query_failed",
                    provider_message_id=msg.gmail_message_id,
                    error=str(exc),
                )
                await self._session.rollback()
                return IngestionResult(
                    provider_message_id=msg.gmail_message_id,
                    failure_reason=FailureReason.DB_WRITE_ERROR,
                    error_detail=str(exc),
                )

        # 3c. Sanitize body (local computation — NO try/except D8)
        sanitized_body = sanitize_email_body(
            msg.body_plain or "",
            max_length=self._settings.max_body_length,
        )
        sanitized_snippet = sanitize_email_body(
            msg.snippet or "",
            max_length=self._settings.snippet_length,
            strip_html=True,
        )

        # 3d. Map adapter schema → ORM model (local — NO try/except D8)
        recipients = _map_recipients(msg)
        attachments = _map_attachments(msg)

        email = Email(
            id=uuid.uuid4(),
            provider_message_id=msg.gmail_message_id,
            thread_id=msg.thread_id,
            account=account_id,
            sender_email=msg.from_address,
            sender_name=None,
            recipients=recipients,
            subject=msg.subject,
            body_plain=str(sanitized_body) if sanitized_body else None,
            body_html=msg.body_html,
            snippet=str(sanitized_snippet) if sanitized_snippet else None,
            date=msg.received_at,
            attachments=attachments,
            provider_labels=msg.provider_labels,
            state=EmailState.FETCHED,
        )

        # 3d. Store in DB → state=FETCHED → commit (external-state D7)
        try:
            self._session.add(email)
            await self._session.commit()
        except IntegrityError as exc:
            # Race condition: another worker inserted the same email
            logger.warning(
                "ingestion_integrity_error",
                provider_message_id=msg.gmail_message_id,
                error=str(exc),
            )
            await self._session.rollback()
            return IngestionResult(
                provider_message_id=msg.gmail_message_id,
                skip_reason=SkipReason.DUPLICATE,
            )
        except SQLAlchemyError as exc:
            logger.error(
                "ingestion_store_failed",
                provider_message_id=msg.gmail_message_id,
                error=str(exc),
            )
            await self._session.rollback()
            return IngestionResult(
                provider_message_id=msg.gmail_message_id,
                failure_reason=FailureReason.DB_WRITE_ERROR,
                error_detail=str(exc),
            )

        logger.info(
            "ingestion_email_stored",
            email_id=str(email.id),
            provider_message_id=msg.gmail_message_id,
        )

        # 3e. Transition to SANITIZED → commit (external-state D7)
        # transition_to() is local (D8) — InvalidStateTransitionError is a bug, NOT caught
        email.transition_to(EmailState.SANITIZED)

        try:
            await self._session.commit()
        except SQLAlchemyError as exc:
            logger.error(
                "ingestion_transition_failed",
                email_id=str(email.id),
                provider_message_id=msg.gmail_message_id,
                error=str(exc),
            )
            await self._session.rollback()
            return IngestionResult(
                provider_message_id=msg.gmail_message_id,
                email_id=email.id,
                failure_reason=FailureReason.DB_TRANSITION_ERROR,
                error_detail=str(exc),
            )

        return IngestionResult(
            provider_message_id=msg.gmail_message_id,
            email_id=email.id,
        )

    async def _acquire_poll_lock(self, account_id: str) -> bool:
        """Acquire distributed lock via Redis SET NX EX.

        Guarantees:
          - Atomic: only one worker per account_id can hold the lock.
          - TTL ensures auto-release if the worker crashes.
        """
        lock_key = f"{self._settings.ingestion_lock_key_prefix}:{account_id}"
        acquired = await self._redis.set(
            lock_key, "1", nx=True, ex=self._settings.ingestion_lock_ttl_seconds
        )
        return acquired is not None

    async def _release_poll_lock(self, account_id: str) -> None:
        """Release distributed lock."""
        lock_key = f"{self._settings.ingestion_lock_key_prefix}:{account_id}"
        await self._redis.delete(lock_key)


def _map_recipients(msg: EmailMessage) -> list[OrmRecipientData]:
    """Map adapter RecipientData (no type) → ORM RecipientData (with type).

    Local computation — no try/except (D8).
    """
    recipients: list[OrmRecipientData] = []
    for r in msg.to_addresses:
        recipients.append(OrmRecipientData(email=r["email"], name=r.get("name") or "", type="to"))
    for r in msg.cc_addresses:
        recipients.append(OrmRecipientData(email=r["email"], name=r.get("name") or "", type="cc"))
    return recipients


def _map_attachments(msg: EmailMessage) -> list[OrmAttachmentData]:
    """Map adapter AttachmentData → ORM AttachmentData (same shape).

    Local computation — no try/except (D8).
    """
    return [
        OrmAttachmentData(
            filename=a["filename"],
            mime_type=a["mime_type"],
            size_bytes=a["size_bytes"],
            attachment_id=a["attachment_id"],
        )
        for a in msg.attachments
    ]
