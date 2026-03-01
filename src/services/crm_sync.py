"""CRM Sync service — orchestrates CRM synchronization for classified emails.

Idempotency check via DB (never CRM API) → contact lookup → conditional
contact creation → activity logging → conditional lead creation → field
updates → persist CRMSyncRecord with independent commit (D13).

Each CRM operation has its own try/except block. There is NO single try
wrapping the entire chain.

contract-docstrings:
  Invariants: CRM adapter must be connected before sync() is called.
  Guarantees: sync() always returns a CRMSyncResult. CRMSyncRecord is
    committed independently (D13) — persists even if caller fails after.
    Partial failure: contact_id populated but activity_id=None is valid.
  Errors raised: CRMAuthError, CRMRateLimitError (re-raised to Celery task),
    SQLAlchemyError on record persist (rollback + raise).
  Errors silenced: CRMAdapterError (generic base) per-operation — recorded
    in CRMOperationStatus, chain continues.
  External state: PostgreSQL (CRMSyncRecord read/write), CRM adapter API.

try-except D7/D8:
  External-state ops (CRM API, DB): structured try/except with specific types.
  Local computation (snippet truncation, field iteration): conditionals only.

pre-mortem:
  Cat 6: CRMSyncRecord committed independently — partial failure recorded.
  Cat 8: All defaults from CRMSyncConfig (sourced from Settings env vars).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.crm.base import CRMAdapter
from src.adapters.crm.exceptions import (
    CRMAdapterError,
    CRMAuthError,
    CRMRateLimitError,
    DuplicateContactError,
)
from src.adapters.crm.schemas import (
    ActivityData,
    ActivityId,
    Contact,
    CreateContactData,
    CreateLeadData,
    LeadId,
)
from src.models.crm_sync import CRMSyncRecord, CRMSyncStatus
from src.services.schemas.crm_sync import (
    CRMOperationStatus,
    CRMSyncConfig,
    CRMSyncRequest,
    CRMSyncResult,
)

logger = structlog.get_logger(__name__)


def _compute_overall_success(operations: list[CRMOperationStatus]) -> bool:
    """Return True if all non-skipped operations succeeded.

    Pure local computation — conditionals only (D8).
    An empty operations list (no contact found, no auto-create) returns False
    because no meaningful CRM sync occurred.
    """
    non_skipped = [op for op in operations if not op.skipped]
    if not non_skipped:
        return False
    return all(op.success for op in non_skipped)


class CRMSyncService:
    """Orchestrates CRM synchronization: idempotency → lookup → create → log → lead → fields.

    Invariants:
      - ``crm_adapter`` must be connected before ``sync()`` is called.
      - ``config`` provides all Cat 8 configurable defaults.

    Guarantees:
      - ``sync()`` always returns a ``CRMSyncResult``.
      - ``CRMSyncRecord`` is committed independently (D13).
      - Partial failure: later operations continue after earlier failures
        (unless contact_id was never obtained).

    Errors raised:
      - ``CRMAuthError``: re-raised to Celery task (no retry).
      - ``CRMRateLimitError``: re-raised to Celery task (retry with backoff).
      - ``SQLAlchemyError`` on persist: rollback + re-raise.

    Errors silenced:
      - ``CRMAdapterError`` (generic base) per-operation: recorded in
        ``CRMOperationStatus``, chain continues.
    """

    def __init__(
        self,
        *,
        crm_adapter: CRMAdapter,
        config: CRMSyncConfig,
    ) -> None:
        self._crm_adapter = crm_adapter
        self._config = config

    async def sync(
        self,
        request: CRMSyncRequest,
        db: AsyncSession,
    ) -> CRMSyncResult:
        """Synchronize email metadata to the CRM.

        Preconditions:
          - CRM adapter is connected.
          - ``request.email_id`` references an existing Email record.
          - ``request.snippet`` is pre-truncated by the caller.

        Guarantees:
          - Returns ``CRMSyncResult`` with all attempted operations recorded.
          - ``CRMSyncRecord`` is committed to DB (D13) before returning.
          - If status=SYNCED already exists, returns cached result without
            any CRM API calls.

        Errors raised:
          - ``CRMAuthError``: token invalid — caller must not retry.
          - ``CRMRateLimitError``: rate limited — caller retries with backoff.
          - ``SQLAlchemyError``: DB persist failed — rollback done, re-raised.

        Errors silenced:
          - ``CRMAdapterError`` (generic): recorded per-operation, sync continues.
        """
        # Step 1: Idempotency check — external state (D7)
        cached = await self._check_idempotency(request.email_id, db)
        if cached is not None:
            logger.info(
                "crm_sync_idempotent_skip",
                email_id=str(request.email_id),
                contact_id=cached.contact_id,
            )
            return self._build_result_from_record(cached, request.email_id)

        operations: list[CRMOperationStatus] = []
        contact_id: str | None = None
        activity_id: str | None = None
        lead_id: str | None = None

        # Step 2: Contact lookup — external state (D7)
        contact_id, lookup_op = await self._do_contact_lookup(request)
        operations.append(lookup_op)

        # Step 3: Contact create (conditional) — external state (D7)
        if contact_id is None and self._config.auto_create_contacts:
            contact_id, create_op = await self._do_contact_create(request)
            operations.append(create_op)

        # Steps 4-6 require contact_id — local gate (D8)
        if contact_id is not None:
            # Step 4: Activity log — external state (D7)
            activity_id, activity_op = await self._do_activity_log(request, contact_id)
            operations.append(activity_op)

            # Step 5: Lead create (conditional) — external state (D7)
            if request.create_lead:
                lead_id, lead_op = await self._do_lead_create(request, contact_id)
                operations.append(lead_op)

            # Step 6: Field updates (conditional) — external state (D7)
            if request.field_updates:
                field_ops = await self._do_field_updates(request, contact_id)
                operations.extend(field_ops)

        # Determine status — local computation (D8)
        # No contact_id means no meaningful sync occurred (short-circuit to False)
        overall_success = contact_id is not None and _compute_overall_success(operations)
        status = CRMSyncStatus.SYNCED if overall_success else CRMSyncStatus.FAILED

        # Step 7: Persist sync record — external state (D7), independent commit (D13)
        record = await self._persist_sync_record(
            db,
            email_id=request.email_id,
            contact_id=contact_id,
            activity_id=activity_id,
            lead_id=lead_id,
            status=status,
        )

        logger.info(
            "crm_sync_complete",
            email_id=str(request.email_id),
            contact_id=contact_id,
            activity_id=activity_id,
            lead_id=lead_id,
            status=status.value,
            operations_count=len(operations),
            overall_success=overall_success,
        )

        return CRMSyncResult(
            email_id=request.email_id,
            contact_id=record.contact_id,
            activity_id=record.activity_id,
            lead_id=record.lead_id,
            operations=operations,
            overall_success=overall_success,
        )

    async def _check_idempotency(
        self,
        email_id: uuid.UUID,
        db: AsyncSession,
    ) -> CRMSyncRecord | None:
        """Check if a SYNCED record already exists for this email.

        External state (D7): SQLAlchemyError caught and returns None,
        treating as fresh sync.

        Returns the most recent CRMSyncRecord if status=SYNCED, else None.
        """
        try:
            result = await db.execute(
                select(CRMSyncRecord)
                .where(CRMSyncRecord.email_id == email_id)
                .order_by(CRMSyncRecord.synced_at.desc())
                .limit(1)
            )
            record = result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            logger.warning(
                "crm_sync_idempotency_check_failed",
                email_id=str(email_id),
                error=str(exc),
            )
            return None

        if record is not None and record.status == CRMSyncStatus.SYNCED:
            return record
        return None

    async def _do_contact_lookup(
        self,
        request: CRMSyncRequest,
    ) -> tuple[str | None, CRMOperationStatus]:
        """Look up contact by sender email.

        External state (D7): CRMAuthError and CRMRateLimitError are re-raised.
        CRMAdapterError is caught, recorded, returns (None, failed_op).

        Returns (contact_id, operation_status).
        """
        try:
            contact: Contact | None = await self._crm_adapter.lookup_contact(request.sender_email)
        except (CRMAuthError, CRMRateLimitError):
            raise
        except CRMAdapterError as exc:
            logger.error(
                "crm_contact_lookup_failed",
                email_id=str(request.email_id),
                error=str(exc),
            )
            return None, CRMOperationStatus(
                operation="contact_lookup",
                success=False,
                error=str(exc),
            )

        if contact is None:
            return None, CRMOperationStatus(
                operation="contact_lookup",
                success=True,
                crm_id=None,
            )

        return contact.id, CRMOperationStatus(
            operation="contact_lookup",
            success=True,
            crm_id=contact.id,
        )

    async def _do_contact_create(
        self,
        request: CRMSyncRequest,
    ) -> tuple[str | None, CRMOperationStatus]:
        """Create a new contact in the CRM.

        External state (D7): CRMAuthError and CRMRateLimitError are re-raised.
        DuplicateContactError triggers re-lookup (race condition handling).
        CRMAdapterError is caught, recorded, returns (None, failed_op).

        Returns (contact_id, operation_status).
        """
        try:
            created: Contact = await self._crm_adapter.create_contact(
                CreateContactData(
                    email=request.sender_email,
                    first_name=request.sender_name,
                    source="mailwise",
                    first_interaction_at=request.received_at,
                )
            )
            return created.id, CRMOperationStatus(
                operation="contact_create",
                success=True,
                crm_id=created.id,
            )
        except (CRMAuthError, CRMRateLimitError):
            raise
        except DuplicateContactError:
            # Race condition: contact was created between our lookup and create.
            # Re-lookup to get the existing contact_id.
            logger.info(
                "crm_duplicate_contact_on_create_re_lookup",
                email_id=str(request.email_id),
            )
            try:
                existing: Contact | None = await self._crm_adapter.lookup_contact(
                    request.sender_email
                )
            except (CRMAuthError, CRMRateLimitError):
                raise
            except CRMAdapterError as exc:
                logger.error(
                    "crm_re_lookup_after_duplicate_failed",
                    email_id=str(request.email_id),
                    error=str(exc),
                )
                return None, CRMOperationStatus(
                    operation="contact_create",
                    success=False,
                    error=f"DuplicateContactError then re-lookup failed: {exc}",
                )

            if existing is not None:
                return existing.id, CRMOperationStatus(
                    operation="contact_create",
                    success=True,
                    crm_id=existing.id,
                )
            return None, CRMOperationStatus(
                operation="contact_create",
                success=False,
                error="DuplicateContactError but contact not found on re-lookup",
            )
        except CRMAdapterError as exc:
            logger.error(
                "crm_contact_create_failed",
                email_id=str(request.email_id),
                error=str(exc),
            )
            return None, CRMOperationStatus(
                operation="contact_create",
                success=False,
                error=str(exc),
            )

    async def _do_activity_log(
        self,
        request: CRMSyncRequest,
        contact_id: str,
    ) -> tuple[str | None, CRMOperationStatus]:
        """Log an activity note associated with the contact.

        External state (D7): CRMAuthError and CRMRateLimitError are re-raised.
        CRMAdapterError is caught, recorded, returns (None, failed_op).

        Snippet is truncated to activity_snippet_length (local computation — D8).

        Returns (activity_id, operation_status).
        """
        truncated_snippet = request.snippet[: self._config.activity_snippet_length]

        try:
            act_id: ActivityId = await self._crm_adapter.log_activity(
                contact_id,
                ActivityData(
                    subject=request.subject,
                    timestamp=request.received_at,
                    classification_action=request.classification_action,
                    classification_type=request.classification_type,
                    snippet=truncated_snippet,
                    email_id=str(request.email_id),
                ),
            )
            return str(act_id), CRMOperationStatus(
                operation="activity_log",
                success=True,
                crm_id=str(act_id),
            )
        except (CRMAuthError, CRMRateLimitError):
            raise
        except CRMAdapterError as exc:
            logger.error(
                "crm_activity_log_failed",
                email_id=str(request.email_id),
                contact_id=contact_id,
                error=str(exc),
            )
            return None, CRMOperationStatus(
                operation="activity_log",
                success=False,
                error=str(exc),
            )

    async def _do_lead_create(
        self,
        request: CRMSyncRequest,
        contact_id: str,
    ) -> tuple[str | None, CRMOperationStatus]:
        """Create a lead (deal) linked to the contact.

        External state (D7): CRMAuthError and CRMRateLimitError are re-raised.
        CRMAdapterError is caught, recorded, returns (None, failed_op).

        Returns (lead_id, operation_status).
        """
        try:
            ld_id: LeadId = await self._crm_adapter.create_lead(
                CreateLeadData(
                    contact_id=contact_id,
                    summary=request.subject,
                    source="mailwise",
                )
            )
            return str(ld_id), CRMOperationStatus(
                operation="lead_create",
                success=True,
                crm_id=str(ld_id),
            )
        except (CRMAuthError, CRMRateLimitError):
            raise
        except CRMAdapterError as exc:
            logger.error(
                "crm_lead_create_failed",
                email_id=str(request.email_id),
                contact_id=contact_id,
                error=str(exc),
            )
            return None, CRMOperationStatus(
                operation="lead_create",
                success=False,
                error=str(exc),
            )

    async def _do_field_updates(
        self,
        request: CRMSyncRequest,
        contact_id: str,
    ) -> list[CRMOperationStatus]:
        """Apply each field update to the contact.

        Per-field try/except (D7): each field update is independent.
        CRMAuthError and CRMRateLimitError re-raised immediately (abort all fields).
        CRMAdapterError per field: recorded, next field continues.

        Note: update_field() returns None (D1 -> None pattern) — bare await.

        Returns list of CRMOperationStatus, one per field.
        """
        results: list[CRMOperationStatus] = []

        for field_name, field_value in request.field_updates.items():
            try:
                await self._crm_adapter.update_field(contact_id, field_name, field_value)
                results.append(
                    CRMOperationStatus(
                        operation="field_update",
                        success=True,
                        crm_id=contact_id,
                    )
                )
            except (CRMAuthError, CRMRateLimitError):
                raise
            except CRMAdapterError as exc:
                logger.warning(
                    "crm_field_update_failed",
                    email_id=str(request.email_id),
                    contact_id=contact_id,
                    field=field_name,
                    error=str(exc),
                )
                results.append(
                    CRMOperationStatus(
                        operation="field_update",
                        success=False,
                        error=str(exc),
                    )
                )

        return results

    async def _persist_sync_record(
        self,
        db: AsyncSession,
        *,
        email_id: uuid.UUID,
        contact_id: str | None,
        activity_id: str | None,
        lead_id: str | None,
        status: CRMSyncStatus,
    ) -> CRMSyncRecord:
        """Persist a CRMSyncRecord with its own independent commit (D13).

        External state (D7): SQLAlchemyError triggers rollback + re-raise.

        Returns the persisted CRMSyncRecord.
        """
        record = CRMSyncRecord(
            id=uuid.uuid4(),
            email_id=email_id,
            contact_id=contact_id,
            activity_id=activity_id,
            lead_id=lead_id,
            status=status,
            synced_at=datetime.now(UTC),
        )
        try:
            db.add(record)
            await db.commit()
        except SQLAlchemyError as exc:
            await db.rollback()
            logger.error(
                "crm_sync_record_persist_failed",
                email_id=str(email_id),
                status=status.value,
                error=str(exc),
            )
            raise

        return record

    def _build_result_from_record(
        self,
        record: CRMSyncRecord,
        email_id: uuid.UUID,
    ) -> CRMSyncResult:
        """Build a CRMSyncResult from an existing CRMSyncRecord (idempotency path).

        Local computation — no try/except (D8).
        """
        return CRMSyncResult(
            email_id=email_id,
            contact_id=record.contact_id,
            activity_id=record.activity_id,
            lead_id=record.lead_id,
            operations=[
                CRMOperationStatus(
                    operation="contact_lookup",
                    success=True,
                    crm_id=record.contact_id,
                    skipped=True,
                )
            ],
            overall_success=record.status == CRMSyncStatus.SYNCED,
        )
