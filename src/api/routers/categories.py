"""Category, few-shot example, and feedback router.

Architecture:
  - ZERO try/except — domain exceptions propagate to exception_handlers.py.
  - Admin for write ops, Reviewer+ for read ops.
  - Literal paths before parameterized paths.

Endpoints (categories_router, prefix /api/v1/categories):
  GET    /actions              — list action categories (Reviewer+)
  POST   /actions              — create action category (Admin, 201)
  PUT    /actions/reorder      — reorder action categories (Admin)
  GET    /actions/{id}         — get single action category (Reviewer+)
  PUT    /actions/{id}         — update action category (Admin)
  DELETE /actions/{id}         — delete with FK guard (Admin, 204)
  (same pattern for /types)

Endpoints (classification_router, prefix /api/v1/classification):
  GET    /examples             — list few-shot examples (Admin)
  POST   /examples             — create example (Admin, 201)
  PUT    /examples/{id}        — update example (Admin)
  DELETE /examples/{id}        — delete example (Admin, 204)
  GET    /feedback             — paginated feedback list (Admin)
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import require_admin, require_reviewer_or_admin
from src.api.schemas.categories import (
    ActionCategoryCreate,
    ActionCategoryResponse,
    ActionCategoryUpdate,
    FeedbackItem,
    FewShotExampleCreate,
    FewShotExampleResponse,
    FewShotExampleUpdate,
    ReorderRequest,
    TypeCategoryCreate,
    TypeCategoryResponse,
    TypeCategoryUpdate,
)
from src.api.schemas.common import PaginatedResponse
from src.core.database import get_async_db
from src.models.category import ActionCategory, TypeCategory
from src.models.feedback import ClassificationFeedback
from src.models.few_shot import FewShotExample
from src.models.user import User
from src.services.category_service import CategoryService

logger = structlog.get_logger(__name__)

categories_router = APIRouter(tags=["categories"])
classification_router = APIRouter(tags=["classification"])

_category_service = CategoryService()


def _action_to_response(cat: ActionCategory) -> ActionCategoryResponse:
    """Map ActionCategory ORM to response schema."""
    return ActionCategoryResponse(
        id=cat.id,
        slug=cat.slug,
        name=cat.name,
        description=cat.description,
        is_fallback=cat.is_fallback,
        is_active=cat.is_active,
        display_order=cat.display_order,
        created_at=cat.created_at,
        updated_at=cat.updated_at,
    )


def _type_to_response(cat: TypeCategory) -> TypeCategoryResponse:
    """Map TypeCategory ORM to response schema."""
    return TypeCategoryResponse(
        id=cat.id,
        slug=cat.slug,
        name=cat.name,
        description=cat.description,
        is_fallback=cat.is_fallback,
        is_active=cat.is_active,
        display_order=cat.display_order,
        created_at=cat.created_at,
        updated_at=cat.updated_at,
    )


def _example_to_response(ex: FewShotExample) -> FewShotExampleResponse:
    """Map FewShotExample ORM to response schema."""
    return FewShotExampleResponse(
        id=ex.id,
        email_snippet=ex.email_snippet,
        action_slug=ex.action_slug,
        type_slug=ex.type_slug,
        rationale=ex.rationale,
        is_active=ex.is_active,
        created_at=ex.created_at,
        updated_at=ex.updated_at,
    )


# ============================================================
# categories_router: /api/v1/categories
# ============================================================

# --- ActionCategory: literal paths BEFORE parameterized ---


@categories_router.get("/actions", response_model=list[ActionCategoryResponse])
async def list_action_categories(
    _current_user: User = Depends(require_reviewer_or_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> list[ActionCategoryResponse]:
    """List all action categories ordered by display_order."""
    cats = await _category_service.list_action_categories(db)
    return [_action_to_response(c) for c in cats]


@categories_router.post(
    "/actions", response_model=ActionCategoryResponse, status_code=status.HTTP_201_CREATED
)
async def create_action_category(
    body: ActionCategoryCreate,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> ActionCategoryResponse:
    """Create a new action category.

    Raises DuplicateResourceError (409) if slug already exists.
    display_order auto-assigned as MAX + 1.
    """
    cat = await _category_service.create_action_category(
        slug=body.slug,
        name=body.name,
        description=body.description,
        is_fallback=body.is_fallback,
        is_active=body.is_active,
        db=db,
    )
    return _action_to_response(cat)


@categories_router.put("/actions/reorder", response_model=list[ActionCategoryResponse])
async def reorder_action_categories(
    body: ReorderRequest,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> list[ActionCategoryResponse]:
    """Bulk reorder action categories.

    ordered_ids[0] receives display_order 1. All IDs must exist.
    Raises NotFoundError if any ID is missing.
    """
    cats = await _category_service.reorder_action_categories(body.ordered_ids, db)
    return [_action_to_response(c) for c in cats]


@categories_router.get("/actions/{category_id}", response_model=ActionCategoryResponse)
async def get_action_category(
    category_id: uuid.UUID,
    _current_user: User = Depends(require_reviewer_or_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> ActionCategoryResponse:
    """Get a single action category by ID.

    Raises NotFoundError if not found.
    """
    cat = await _category_service.get_action_category(category_id, db)
    return _action_to_response(cat)


@categories_router.put("/actions/{category_id}", response_model=ActionCategoryResponse)
async def update_action_category(
    category_id: uuid.UUID,
    body: ActionCategoryUpdate,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> ActionCategoryResponse:
    """Partial update of an action category. Slug is immutable.

    Only non-None fields are applied.
    Raises NotFoundError if category does not exist.
    """
    cat = await _category_service.update_action_category(
        category_id,
        db,
        name=body.name,
        description=body.description,
        is_fallback=body.is_fallback,
        is_active=body.is_active,
    )
    return _action_to_response(cat)


@categories_router.delete("/actions/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_action_category(
    category_id: uuid.UUID,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> None:
    """Delete an action category. Returns 204 No Content.

    Raises NotFoundError if category does not exist.
    Raises CategoryInUseError (409) if referenced by classifications or feedback.
    """
    await _category_service.delete_action_category(category_id, db)
    logger.info("action_category_deleted", category_id=str(category_id))


# --- TypeCategory: literal paths BEFORE parameterized ---


@categories_router.get("/types", response_model=list[TypeCategoryResponse])
async def list_type_categories(
    _current_user: User = Depends(require_reviewer_or_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> list[TypeCategoryResponse]:
    """List all type categories ordered by display_order."""
    cats = await _category_service.list_type_categories(db)
    return [_type_to_response(c) for c in cats]


@categories_router.post(
    "/types", response_model=TypeCategoryResponse, status_code=status.HTTP_201_CREATED
)
async def create_type_category(
    body: TypeCategoryCreate,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> TypeCategoryResponse:
    """Create a new type category.

    Raises DuplicateResourceError (409) if slug already exists.
    """
    cat = await _category_service.create_type_category(
        slug=body.slug,
        name=body.name,
        description=body.description,
        is_fallback=body.is_fallback,
        is_active=body.is_active,
        db=db,
    )
    return _type_to_response(cat)


@categories_router.put("/types/reorder", response_model=list[TypeCategoryResponse])
async def reorder_type_categories(
    body: ReorderRequest,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> list[TypeCategoryResponse]:
    """Bulk reorder type categories.

    ordered_ids[0] receives display_order 1. All IDs must exist.
    Raises NotFoundError if any ID is missing.
    """
    cats = await _category_service.reorder_type_categories(body.ordered_ids, db)
    return [_type_to_response(c) for c in cats]


@categories_router.get("/types/{category_id}", response_model=TypeCategoryResponse)
async def get_type_category(
    category_id: uuid.UUID,
    _current_user: User = Depends(require_reviewer_or_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> TypeCategoryResponse:
    """Get a single type category by ID.

    Raises NotFoundError if not found.
    """
    cat = await _category_service.get_type_category(category_id, db)
    return _type_to_response(cat)


@categories_router.put("/types/{category_id}", response_model=TypeCategoryResponse)
async def update_type_category(
    category_id: uuid.UUID,
    body: TypeCategoryUpdate,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> TypeCategoryResponse:
    """Partial update of a type category. Slug is immutable.

    Only non-None fields are applied.
    Raises NotFoundError if category does not exist.
    """
    cat = await _category_service.update_type_category(
        category_id,
        db,
        name=body.name,
        description=body.description,
        is_fallback=body.is_fallback,
        is_active=body.is_active,
    )
    return _type_to_response(cat)


@categories_router.delete("/types/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_type_category(
    category_id: uuid.UUID,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> None:
    """Delete a type category. Returns 204 No Content.

    Raises NotFoundError if category does not exist.
    Raises CategoryInUseError (409) if referenced by classifications or feedback.
    """
    await _category_service.delete_type_category(category_id, db)
    logger.info("type_category_deleted", category_id=str(category_id))


# ============================================================
# classification_router: /api/v1/classification
# ============================================================

# --- FewShotExample CRUD ---


@classification_router.get("/examples", response_model=list[FewShotExampleResponse])
async def list_examples(
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> list[FewShotExampleResponse]:
    """List all few-shot examples ordered by created_at descending."""
    result = await db.execute(select(FewShotExample).order_by(FewShotExample.created_at.desc()))
    examples = list(result.scalars().all())
    return [_example_to_response(ex) for ex in examples]


@classification_router.post(
    "/examples",
    response_model=FewShotExampleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_example(
    body: FewShotExampleCreate,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> FewShotExampleResponse:
    """Create a new few-shot example. Returns 201 Created."""
    now = datetime.now(UTC)
    example = FewShotExample(
        id=uuid.uuid4(),
        email_snippet=body.email_snippet,
        action_slug=body.action_slug,
        type_slug=body.type_slug,
        rationale=body.rationale,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(example)
    await db.flush()
    await db.refresh(example)

    logger.info("few_shot_example_created", example_id=str(example.id))
    return _example_to_response(example)


@classification_router.put("/examples/{example_id}", response_model=FewShotExampleResponse)
async def update_example(
    example_id: uuid.UUID,
    body: FewShotExampleUpdate,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> FewShotExampleResponse:
    """Partial update of a few-shot example. Only non-None fields are applied.

    Raises NotFoundError if example does not exist.
    """
    from src.core.exceptions import NotFoundError

    result = await db.execute(select(FewShotExample).where(FewShotExample.id == example_id))
    example = result.scalar_one_or_none()
    if example is None:
        raise NotFoundError(f"FewShotExample {example_id} not found")

    if body.email_snippet is not None:
        example.email_snippet = body.email_snippet
    if body.action_slug is not None:
        example.action_slug = body.action_slug
    if body.type_slug is not None:
        example.type_slug = body.type_slug
    if body.rationale is not None:
        example.rationale = body.rationale
    if body.is_active is not None:
        example.is_active = body.is_active

    await db.flush()
    await db.refresh(example)

    logger.info("few_shot_example_updated", example_id=str(example_id))
    return _example_to_response(example)


@classification_router.delete("/examples/{example_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_example(
    example_id: uuid.UUID,
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> None:
    """Delete a few-shot example. Returns 204 No Content.

    Raises NotFoundError if example does not exist.
    """
    from src.core.exceptions import NotFoundError

    result = await db.execute(select(FewShotExample).where(FewShotExample.id == example_id))
    example = result.scalar_one_or_none()
    if example is None:
        raise NotFoundError(f"FewShotExample {example_id} not found")

    await db.delete(example)
    logger.info("few_shot_example_deleted", example_id=str(example_id))


# --- Feedback list (read-only, paginated, JOIN to resolve slugs) ---


@classification_router.get("/feedback", response_model=PaginatedResponse[FeedbackItem])
async def list_feedback(
    page: int = Query(default=1, ge=1),  # noqa: B008
    page_size: int = Query(default=20, ge=1, le=100),  # noqa: B008
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> PaginatedResponse[FeedbackItem]:
    """Paginated list of classification feedback with resolved category slugs.

    JOINs with ActionCategory and TypeCategory to resolve UUIDs to slugs.
    """
    from sqlalchemy import func

    from src.models.category import ActionCategory, TypeCategory

    # Aliases for the four category JOINs
    OrigAction = ActionCategory.__table__.alias("orig_action")
    OrigType = TypeCategory.__table__.alias("orig_type")
    CorrAction = ActionCategory.__table__.alias("corr_action")
    CorrType = TypeCategory.__table__.alias("corr_type")

    # Count query
    count_result = await db.execute(select(func.count(ClassificationFeedback.id)))
    total: int = count_result.scalar_one()

    # Paginated fetch with JOINs
    offset = (page - 1) * page_size
    stmt = (
        select(
            ClassificationFeedback.id,
            ClassificationFeedback.email_id,
            OrigAction.c.slug.label("original_action"),
            OrigType.c.slug.label("original_type"),
            CorrAction.c.slug.label("corrected_action"),
            CorrType.c.slug.label("corrected_type"),
            ClassificationFeedback.corrected_by,
            ClassificationFeedback.corrected_at,
        )
        .join(OrigAction, ClassificationFeedback.original_action_id == OrigAction.c.id)
        .join(OrigType, ClassificationFeedback.original_type_id == OrigType.c.id)
        .join(CorrAction, ClassificationFeedback.corrected_action_id == CorrAction.c.id)
        .join(CorrType, ClassificationFeedback.corrected_type_id == CorrType.c.id)
        .order_by(ClassificationFeedback.corrected_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    rows = result.all()

    items = [
        FeedbackItem(
            id=row.id,
            email_id=row.email_id,
            original_action=row.original_action,
            original_type=row.original_type,
            corrected_action=row.corrected_action,
            corrected_type=row.corrected_type,
            corrected_by=row.corrected_by,
            corrected_at=row.corrected_at,
        )
        for row in rows
    ]

    pages = math.ceil(total / page_size) if total > 0 else 0
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )
