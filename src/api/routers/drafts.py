"""Draft router — list, detail, approve, reject, reassign.

Architecture:
  - ZERO try/except — domain exceptions propagate to exception_handlers.py.
  - Access control: Reviewer sees only own drafts, Admin sees all.
  - require_draft_access dependency handles load + authorization for most endpoints.

Endpoints:
  GET    /              — paginated draft list (scoped by role)
  GET    /{draft_id}    — draft detail with email context for review
  POST   /{draft_id}/approve   — approve draft for sending
  POST   /{draft_id}/reject    — reject draft (204)
  POST   /{draft_id}/reassign  — reassign reviewer (admin only)
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import require_admin, require_draft_access, require_reviewer_or_admin
from src.api.schemas.common import PaginatedResponse
from src.api.schemas.drafts import (
    DraftApproveRequest,
    DraftApproveResponse,
    DraftDetailResponse,
    DraftListItem,
    DraftReassignRequest,
    DraftRejectRequest,
    EmailForDraftReview,
)
from src.api.schemas.emails import ClassificationSummary, PaginationParams
from src.core.database import get_async_db
from src.core.exceptions import InvalidStateTransitionError, NotFoundError
from src.models.category import ActionCategory, TypeCategory
from src.models.classification import ClassificationResult
from src.models.draft import Draft, DraftStatus
from src.models.email import Email
from src.models.user import User, UserRole

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["drafts"])


@router.get("/", response_model=PaginatedResponse[DraftListItem])
async def list_drafts(
    pagination: PaginationParams = Depends(),  # noqa: B008
    draft_status: str | None = Query(default=None, alias="status"),  # noqa: B008
    current_user: User = Depends(require_reviewer_or_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> PaginatedResponse[DraftListItem]:
    """List drafts with pagination.

    Admin sees all drafts. Reviewer sees only drafts assigned to them.
    Optional status filter narrows results.
    """
    base_q = select(Draft)

    # Scope by role
    if current_user.role == UserRole.REVIEWER:
        base_q = base_q.where(Draft.reviewer_id == current_user.id)

    # Optional status filter
    if draft_status is not None:
        base_q = base_q.where(Draft.status == draft_status)

    # Count total
    count_q = select(func.count()).select_from(base_q.subquery())
    total_result = await db.execute(count_q)
    total: int = total_result.scalar_one()

    # Paginated fetch ordered by created_at descending
    page_q = (
        base_q.order_by(Draft.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    drafts_result = await db.execute(page_q)
    drafts = list(drafts_result.scalars().all())

    # Load associated emails for subject/sender
    email_ids = [d.email_id for d in drafts]
    email_map: dict[uuid.UUID, Email] = {}
    if email_ids:
        emails_result = await db.execute(select(Email).where(Email.id.in_(email_ids)))
        email_map = {e.id: e for e in emails_result.scalars().all()}

    items: list[DraftListItem] = []
    for draft in drafts:
        email = email_map.get(draft.email_id)
        items.append(
            DraftListItem(
                id=draft.id,
                email_id=draft.email_id,
                email_subject=email.subject if email else "",
                email_sender=email.sender_email if email else "",
                status=str(draft.status),
                reviewer_id=draft.reviewer_id,
                created_at=draft.created_at,
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


@router.get("/{draft_id}", response_model=DraftDetailResponse)
async def get_draft(
    draft: Draft = Depends(require_draft_access),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> DraftDetailResponse:
    """Draft detail with email context for side-by-side review.

    require_draft_access handles load + authorization (Admin all, Reviewer own).
    body_plain excluded from email context (PII policy).
    """
    email_result = await db.execute(select(Email).where(Email.id == draft.email_id))
    email = email_result.scalar_one_or_none()
    if email is None:
        raise NotFoundError(f"Email {draft.email_id} not found")

    # Load classification for this email (optional)
    clf_result = await db.execute(
        select(ClassificationResult).where(ClassificationResult.email_id == email.id)
    )
    clf = clf_result.scalar_one_or_none()

    classification: ClassificationSummary | None = None
    if clf is not None:
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

    email_for_review = EmailForDraftReview(
        id=email.id,
        subject=email.subject,
        sender_email=email.sender_email,
        sender_name=email.sender_name,
        snippet=email.snippet,
        received_at=email.date,
        classification=classification,
    )

    return DraftDetailResponse(
        id=draft.id,
        content=draft.content,
        status=str(draft.status),
        reviewer_id=draft.reviewer_id,
        reviewed_at=draft.reviewed_at,
        pushed_to_provider=draft.pushed_to_provider,
        email=email_for_review,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )


@router.post("/{draft_id}/approve", response_model=DraftApproveResponse)
async def approve_draft(
    _body: DraftApproveRequest,
    draft: Draft = Depends(require_draft_access),  # noqa: B008
    current_user: User = Depends(require_reviewer_or_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> DraftApproveResponse:
    """Approve a pending draft.

    Gmail push deferred to B14. Sets pushed_to_provider=False, gmail_draft_id=None.
    Raises InvalidStateTransitionError if draft is not PENDING.
    """
    if draft.status != DraftStatus.PENDING:
        raise InvalidStateTransitionError(
            f"Draft {draft.id} cannot be approved from status {draft.status}. "
            "Only PENDING drafts can be approved."
        )

    reviewed_at = datetime.now(UTC)
    draft.status = DraftStatus.APPROVED
    draft.reviewer_id = current_user.id
    draft.reviewed_at = reviewed_at

    # Gmail push deferred to B14
    draft.pushed_to_provider = False

    logger.info("draft_approved", draft_id=str(draft.id), reviewer_id=str(current_user.id))

    return DraftApproveResponse(
        draft_id=draft.id,
        approved=True,
        gmail_draft_id=None,
        approved_at=reviewed_at,
        note="Gmail push deferred — pending B14 implementation",
    )


@router.post("/{draft_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_draft(
    _body: DraftRejectRequest,
    draft: Draft = Depends(require_draft_access),  # noqa: B008
    current_user: User = Depends(require_reviewer_or_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> None:
    """Reject a pending draft. Returns 204 No Content.

    Raises InvalidStateTransitionError if draft is not PENDING.
    """
    if draft.status != DraftStatus.PENDING:
        raise InvalidStateTransitionError(
            f"Draft {draft.id} cannot be rejected from status {draft.status}. "
            "Only PENDING drafts can be rejected."
        )

    draft.status = DraftStatus.REJECTED
    draft.reviewer_id = current_user.id
    draft.reviewed_at = datetime.now(UTC)

    logger.info("draft_rejected", draft_id=str(draft.id), reviewer_id=str(current_user.id))


@router.post("/{draft_id}/reassign", response_model=DraftDetailResponse)
async def reassign_draft(
    draft_id: uuid.UUID,
    body: DraftReassignRequest,
    current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> DraftDetailResponse:
    """Reassign draft to a different reviewer (admin only).

    Uses require_admin (not require_draft_access) — admin has unrestricted access.
    Raises NotFoundError if draft or new reviewer not found.
    """
    # Load draft by draft_id directly (admin, no scoping)
    draft_result = await db.execute(select(Draft).where(Draft.id == draft_id))
    draft = draft_result.scalar_one_or_none()
    if draft is None:
        raise NotFoundError(f"Draft {draft_id} not found")

    # Verify new reviewer exists
    reviewer_result = await db.execute(select(User).where(User.id == body.reviewer_id))
    new_reviewer = reviewer_result.scalar_one_or_none()
    if new_reviewer is None:
        raise NotFoundError(f"User {body.reviewer_id} not found")

    draft.reviewer_id = body.reviewer_id
    await db.flush()
    await db.refresh(draft)

    logger.info(
        "draft_reassigned",
        draft_id=str(draft_id),
        new_reviewer_id=str(body.reviewer_id),
        admin_id=str(current_user.id),
    )

    # Load email for response
    email_result = await db.execute(select(Email).where(Email.id == draft.email_id))
    email = email_result.scalar_one_or_none()
    if email is None:
        raise NotFoundError(f"Email {draft.email_id} not found")

    # Load classification (optional)
    clf_result = await db.execute(
        select(ClassificationResult).where(ClassificationResult.email_id == email.id)
    )
    clf = clf_result.scalar_one_or_none()

    classification: ClassificationSummary | None = None
    if clf is not None:
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

    email_for_review = EmailForDraftReview(
        id=email.id,
        subject=email.subject,
        sender_email=email.sender_email,
        sender_name=email.sender_name,
        snippet=email.snippet,
        received_at=email.date,
        classification=classification,
    )

    return DraftDetailResponse(
        id=draft.id,
        content=draft.content,
        status=str(draft.status),
        reviewer_id=draft.reviewer_id,
        reviewed_at=draft.reviewed_at,
        pushed_to_provider=draft.pushed_to_provider,
        email=email_for_review,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )
