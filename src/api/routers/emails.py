"""Email router — list, detail, retry, reclassify, classification, feedback.

Architecture:
  - ZERO try/except — domain exceptions propagate to exception_handlers.py.
  - No direct adapter imports — uses services and deps.
  - Thin layer: query DB, map ORM to schema, return.

Endpoints:
  GET    /             — paginated email list with optional filters
  GET    /{email_id}   — full email detail (no body_plain, PII policy)
  POST   /{email_id}/retry          — re-queue failed email (admin only)
  POST   /{email_id}/reclassify     — reset to SANITIZED and re-classify (admin only)
  GET    /{email_id}/classification — classification detail
  POST   /{email_id}/classification/feedback — reviewer correction (201)
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import require_admin, require_reviewer_or_admin
from src.api.schemas.common import PaginatedResponse
from src.api.schemas.emails import (
    ClassificationDetailResponse,
    ClassificationFeedbackRequest,
    ClassificationSummary,
    CRMSyncSummary,
    DraftSummary,
    EmailDetailResponse,
    EmailFilter,
    EmailListItem,
    FeedbackResponse,
    PaginationParams,
    ReclassifyRequest,
    ReclassifyResponse,
    RetryRequest,
    RetryResponse,
    RoutingActionSummary,
)
from src.core.database import get_async_db
from src.core.exceptions import InvalidStateTransitionError, NotFoundError
from src.models.category import ActionCategory, TypeCategory
from src.models.classification import ClassificationResult
from src.models.crm_sync import CRMSyncRecord
from src.models.draft import Draft
from src.models.email import Email, EmailState
from src.models.feedback import ClassificationFeedback
from src.models.routing import RoutingAction
from src.models.user import User
from src.tasks.pipeline import classify_task, run_pipeline

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["emails"])

# Failed states eligible for pipeline retry
_FAILED_STATES: frozenset[EmailState] = frozenset(
    {
        EmailState.CLASSIFICATION_FAILED,
        EmailState.ROUTING_FAILED,
        EmailState.CRM_SYNC_FAILED,
        EmailState.DRAFT_FAILED,
    }
)

# States where reclassification is allowed (must have passed ingestion at minimum)
_RECLASSIFIABLE_STATES: frozenset[EmailState] = frozenset(
    {
        EmailState.CLASSIFIED,
        EmailState.ROUTED,
        EmailState.CRM_SYNCED,
        EmailState.DRAFT_GENERATED,
        EmailState.COMPLETED,
        EmailState.RESPONDED,
        EmailState.CLASSIFICATION_FAILED,
        EmailState.ROUTING_FAILED,
        EmailState.CRM_SYNC_FAILED,
        EmailState.DRAFT_FAILED,
    }
)


@router.get("/", response_model=PaginatedResponse[EmailListItem])
async def list_emails(
    pagination: PaginationParams = Depends(),  # noqa: B008
    filters: EmailFilter = Depends(),  # noqa: B008
    _current_user: User = Depends(require_reviewer_or_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> PaginatedResponse[EmailListItem]:
    """List emails with optional filters and pagination.

    Returns emails ordered by date descending. Classification summary included
    when available. body_plain excluded (PII policy).
    """
    # Build base query
    base_q = select(Email)

    if filters.state is not None:
        base_q = base_q.where(Email.state == filters.state)

    if filters.sender is not None:
        base_q = base_q.where(Email.sender_email.ilike(f"%{filters.sender}%"))

    if filters.date_from is not None:
        base_q = base_q.where(Email.date >= filters.date_from)

    if filters.date_to is not None:
        base_q = base_q.where(Email.date <= filters.date_to)

    # Filter by action/type slug requires joining ClassificationResult + categories
    if filters.action is not None:
        action_cat_subq = (
            select(ActionCategory.id).where(ActionCategory.slug == filters.action).scalar_subquery()
        )
        clf_subq = select(ClassificationResult.email_id).where(
            ClassificationResult.action_category_id == action_cat_subq
        )
        base_q = base_q.where(Email.id.in_(clf_subq))

    if filters.type is not None:
        type_cat_subq = (
            select(TypeCategory.id).where(TypeCategory.slug == filters.type).scalar_subquery()
        )
        clf_subq_type = select(ClassificationResult.email_id).where(
            ClassificationResult.type_category_id == type_cat_subq
        )
        base_q = base_q.where(Email.id.in_(clf_subq_type))

    # Count total
    count_q = select(func.count()).select_from(base_q.subquery())
    total_result = await db.execute(count_q)
    total: int = total_result.scalar_one()

    # Paginated fetch ordered by date descending
    page_q = (
        base_q.order_by(Email.date.desc()).offset(pagination.offset).limit(pagination.page_size)
    )
    emails_result = await db.execute(page_q)
    emails = list(emails_result.scalars().all())

    # Load classifications for all fetched emails in one query
    if emails:
        email_ids = [e.id for e in emails]
        clf_q = select(ClassificationResult).where(ClassificationResult.email_id.in_(email_ids))
        clf_result = await db.execute(clf_q)
        clf_map: dict[uuid.UUID, ClassificationResult] = {
            c.email_id: c for c in clf_result.scalars().all()
        }

        # Load category slugs for the classifications we have
        clf_records = list(clf_map.values())
        action_ids = list({c.action_category_id for c in clf_records})
        type_ids = list({c.type_category_id for c in clf_records})

        action_cats: dict[uuid.UUID, str] = {}
        type_cats: dict[uuid.UUID, str] = {}

        if action_ids:
            ac_q = select(ActionCategory).where(ActionCategory.id.in_(action_ids))
            ac_result = await db.execute(ac_q)
            action_cats = {a.id: a.slug for a in ac_result.scalars().all()}

        if type_ids:
            tc_q = select(TypeCategory).where(TypeCategory.id.in_(type_ids))
            tc_result = await db.execute(tc_q)
            type_cats = {t.id: t.slug for t in tc_result.scalars().all()}
    else:
        clf_map = {}
        action_cats = {}
        type_cats = {}

    # Build response items
    items: list[EmailListItem] = []
    for email in emails:
        clf = clf_map.get(email.id)
        classification: ClassificationSummary | None = None
        if clf is not None:
            classification = ClassificationSummary(
                action=action_cats.get(clf.action_category_id, "unknown"),
                type=type_cats.get(clf.type_category_id, "unknown"),
                confidence=str(clf.confidence),
                is_fallback=clf.fallback_applied,
            )
        items.append(
            EmailListItem(
                id=email.id,
                subject=email.subject,
                sender_email=email.sender_email,
                sender_name=email.sender_name,
                received_at=email.date,
                state=email.state,
                snippet=email.snippet,
                classification=classification,
            )
        )

    pages = math.ceil(total / pagination.page_size) if total > 0 else 0
    return PaginatedResponse(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=pages,
    )


@router.get("/{email_id}", response_model=EmailDetailResponse)
async def get_email(
    email_id: uuid.UUID,
    _current_user: User = Depends(require_reviewer_or_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> EmailDetailResponse:
    """Full email detail including all pipeline stages.

    body_plain excluded (PII policy). Classification, routing actions, CRM sync,
    and draft summary included when present.
    """
    result = await db.execute(select(Email).where(Email.id == email_id))
    email = result.scalar_one_or_none()
    if email is None:
        raise NotFoundError(f"Email {email_id} not found")

    # Load classification (optional)
    clf_result = await db.execute(
        select(ClassificationResult).where(ClassificationResult.email_id == email_id)
    )
    clf = clf_result.scalar_one_or_none()

    classification: ClassificationSummary | None = None
    if clf is not None:
        # Resolve category slugs
        ac_result = await db.execute(
            select(ActionCategory).where(ActionCategory.id == clf.action_category_id)
        )
        action_cat = ac_result.scalar_one_or_none()

        tc_result = await db.execute(
            select(TypeCategory).where(TypeCategory.id == clf.type_category_id)
        )
        type_cat = tc_result.scalar_one_or_none()

        classification = ClassificationSummary(
            action=action_cat.slug if action_cat else "unknown",
            type=type_cat.slug if type_cat else "unknown",
            confidence=str(clf.confidence),
            is_fallback=clf.fallback_applied,
        )

    # Load routing actions
    ra_result = await db.execute(select(RoutingAction).where(RoutingAction.email_id == email_id))
    routing_actions_orm = list(ra_result.scalars().all())
    routing_actions = [
        RoutingActionSummary(
            id=ra.id,
            channel=ra.channel,
            destination=ra.destination,
            status=str(ra.status),
            dispatched_at=ra.dispatched_at,
        )
        for ra in routing_actions_orm
    ]

    # Load CRM sync record (first match)
    crm_result = await db.execute(
        select(CRMSyncRecord).where(CRMSyncRecord.email_id == email_id).limit(1)
    )
    crm_record = crm_result.scalar_one_or_none()
    crm_sync: CRMSyncSummary | None = None
    if crm_record is not None:
        crm_sync = CRMSyncSummary(
            status=str(crm_record.status),
            contact_id=crm_record.contact_id,
            activity_id=crm_record.activity_id,
            synced_at=crm_record.synced_at,
        )

    # Load draft (first match)
    draft_result = await db.execute(select(Draft).where(Draft.email_id == email_id).limit(1))
    draft_orm = draft_result.scalar_one_or_none()
    draft_summary: DraftSummary | None = None
    if draft_orm is not None:
        draft_summary = DraftSummary(
            id=draft_orm.id,
            status=str(draft_orm.status),
            created_at=draft_orm.created_at,
        )

    return EmailDetailResponse(
        id=email.id,
        subject=email.subject,
        sender_email=email.sender_email,
        sender_name=email.sender_name,
        received_at=email.date,
        state=email.state,
        snippet=email.snippet,
        thread_id=email.thread_id,
        classification=classification,
        routing_actions=routing_actions,
        crm_sync=crm_sync,
        draft=draft_summary,
        created_at=email.created_at,
        updated_at=email.updated_at,
    )


@router.post("/{email_id}/retry", response_model=RetryResponse)
async def retry_email(
    email_id: uuid.UUID,
    _body: RetryRequest,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> RetryResponse:
    """Re-queue a failed email through the pipeline.

    Email must be in a *_FAILED state. Raises InvalidStateTransitionError
    if the email is not failed.
    """
    result = await db.execute(select(Email).where(Email.id == email_id))
    email = result.scalar_one_or_none()
    if email is None:
        raise NotFoundError(f"Email {email_id} not found")

    if email.state not in _FAILED_STATES:
        raise InvalidStateTransitionError(
            f"Email {email_id} is not in a failed state (current: {email.state}). "
            f"Retry only allowed for: {', '.join(sorted(_FAILED_STATES))}"
        )

    logger.info("email_retry_queued", email_id=str(email_id))
    run_pipeline(email.id)

    return RetryResponse(
        queued=True,
        message="Pipeline retry queued",
        email_id=email.id,
    )


@router.post("/{email_id}/reclassify", response_model=ReclassifyResponse)
async def reclassify_email(
    email_id: uuid.UUID,
    _body: ReclassifyRequest,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> ReclassifyResponse:
    """Reset email to SANITIZED and re-queue classification (admin power operation).

    Email must have passed ingestion (not FETCHED/SANITIZED). Direct state
    assignment bypasses normal state machine — admin power op.
    """
    result = await db.execute(select(Email).where(Email.id == email_id))
    email = result.scalar_one_or_none()
    if email is None:
        raise NotFoundError(f"Email {email_id} not found")

    if email.state not in _RECLASSIFIABLE_STATES:
        raise InvalidStateTransitionError(
            f"Email {email_id} cannot be reclassified from state {email.state}. "
            f"Must be past ingestion (CLASSIFIED or later, or a failed state)."
        )

    # Direct state assignment — admin bypasses state machine
    email.state = EmailState.SANITIZED
    await db.flush()

    logger.info("email_reclassify_queued", email_id=str(email_id))
    classify_task.delay(str(email.id))

    return ReclassifyResponse(
        queued=True,
        message="Reclassification queued",
        email_id=email.id,
    )


@router.get("/{email_id}/classification", response_model=ClassificationDetailResponse)
async def get_classification(
    email_id: uuid.UUID,
    _current_user: User = Depends(require_reviewer_or_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> ClassificationDetailResponse:
    """Return the classification result for an email."""
    clf_result = await db.execute(
        select(ClassificationResult).where(ClassificationResult.email_id == email_id)
    )
    clf = clf_result.scalar_one_or_none()
    if clf is None:
        raise NotFoundError(f"Classification for email {email_id} not found")

    # Resolve category slugs
    ac_result = await db.execute(
        select(ActionCategory).where(ActionCategory.id == clf.action_category_id)
    )
    action_cat = ac_result.scalar_one_or_none()

    tc_result = await db.execute(
        select(TypeCategory).where(TypeCategory.id == clf.type_category_id)
    )
    type_cat = tc_result.scalar_one_or_none()

    return ClassificationDetailResponse(
        id=clf.id,
        email_id=clf.email_id,
        action=action_cat.slug if action_cat else "unknown",
        type=type_cat.slug if type_cat else "unknown",
        confidence=str(clf.confidence),
        is_fallback=clf.fallback_applied,
        classified_at=clf.classified_at,
    )


@router.post(
    "/{email_id}/classification/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_classification_feedback(
    email_id: uuid.UUID,
    body: ClassificationFeedbackRequest,
    current_user: User = Depends(require_reviewer_or_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> FeedbackResponse:
    """Submit reviewer correction for a misclassified email.

    Resolves corrected action/type slugs to category IDs. Raises NotFoundError
    if the email, its classification, or the provided slugs do not exist.
    """
    # Verify email exists
    email_result = await db.execute(select(Email).where(Email.id == email_id))
    if email_result.scalar_one_or_none() is None:
        raise NotFoundError(f"Email {email_id} not found")

    # Load classification for the email
    clf_result = await db.execute(
        select(ClassificationResult).where(ClassificationResult.email_id == email_id)
    )
    clf = clf_result.scalar_one_or_none()
    if clf is None:
        raise NotFoundError(f"Classification for email {email_id} not found")

    # Resolve corrected_action slug → ActionCategory.id
    corrected_ac_result = await db.execute(
        select(ActionCategory).where(ActionCategory.slug == body.corrected_action)
    )
    corrected_action_cat = corrected_ac_result.scalar_one_or_none()
    if corrected_action_cat is None:
        raise NotFoundError(f"Action category '{body.corrected_action}' not found")

    # Resolve corrected_type slug → TypeCategory.id
    corrected_tc_result = await db.execute(
        select(TypeCategory).where(TypeCategory.slug == body.corrected_type)
    )
    corrected_type_cat = corrected_tc_result.scalar_one_or_none()
    if corrected_type_cat is None:
        raise NotFoundError(f"Type category '{body.corrected_type}' not found")

    feedback = ClassificationFeedback(
        id=uuid.uuid4(),
        email_id=email_id,
        original_action_id=clf.action_category_id,
        original_type_id=clf.type_category_id,
        corrected_action_id=corrected_action_cat.id,
        corrected_type_id=corrected_type_cat.id,
        corrected_by=current_user.id,
        corrected_at=datetime.now(UTC),
    )
    db.add(feedback)
    await db.flush()

    logger.info(
        "classification_feedback_recorded",
        email_id=str(email_id),
        corrected_action=body.corrected_action,
        corrected_type=body.corrected_type,
    )

    return FeedbackResponse(recorded=True, feedback_id=feedback.id)
