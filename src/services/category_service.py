"""Category management service — CRUD, FK guard, reorder.

Architecture:
  - DB operations wrapped in try/except SQLAlchemyError (external state).
  - Category deletion uses explicit count query to guard foreign key references.
  - Session managed by DI: flush + refresh, NOT commit.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import CategoryInUseError, DuplicateResourceError, NotFoundError
from src.models.category import ActionCategory, TypeCategory
from src.models.classification import ClassificationResult
from src.models.feedback import ClassificationFeedback

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class CategoryService:
    """Business logic for ActionCategory and TypeCategory management."""

    # --- ActionCategory ---

    async def list_action_categories(self, db: AsyncSession) -> list[ActionCategory]:
        """List all action categories ordered by display_order."""
        result = await db.execute(
            select(ActionCategory).order_by(ActionCategory.display_order.asc())
        )
        return list(result.scalars().all())

    async def get_action_category(self, category_id: uuid.UUID, db: AsyncSession) -> ActionCategory:
        """Get a single action category. Raises NotFoundError if missing."""
        result = await db.execute(select(ActionCategory).where(ActionCategory.id == category_id))
        category = result.scalar_one_or_none()
        if category is None:
            raise NotFoundError(f"Action category {category_id} not found")
        return category

    async def create_action_category(
        self,
        slug: str,
        name: str,
        description: str,
        is_fallback: bool,
        is_active: bool,
        db: AsyncSession,
    ) -> ActionCategory:
        """Create an action category. Raises DuplicateResourceError if slug exists."""
        existing = await db.execute(select(ActionCategory).where(ActionCategory.slug == slug))
        if existing.scalar_one_or_none() is not None:
            raise DuplicateResourceError(f"Action category slug '{slug}' already exists")

        # Auto-assign display_order as MAX + 1
        max_result = await db.execute(select(func.max(ActionCategory.display_order)))
        max_order: int | None = max_result.scalar_one_or_none()
        next_order = (max_order or 0) + 1

        category = ActionCategory(
            id=uuid.uuid4(),
            slug=slug,
            name=name,
            description=description,
            is_fallback=is_fallback,
            is_active=is_active,
            display_order=next_order,
        )
        db.add(category)
        await db.flush()
        await db.refresh(category)

        logger.info("action_category_created", category_id=str(category.id), slug=slug)
        return category

    async def update_action_category(
        self,
        category_id: uuid.UUID,
        db: AsyncSession,
        *,
        name: str | None = None,
        description: str | None = None,
        is_fallback: bool | None = None,
        is_active: bool | None = None,
    ) -> ActionCategory:
        """Partial update of an action category. Slug is immutable."""
        category = await self.get_action_category(category_id, db)
        if name is not None:
            category.name = name
        if description is not None:
            category.description = description
        if is_fallback is not None:
            category.is_fallback = is_fallback
        if is_active is not None:
            category.is_active = is_active
        await db.flush()
        await db.refresh(category)
        logger.info("action_category_updated", category_id=str(category_id))
        return category

    async def delete_action_category(self, category_id: uuid.UUID, db: AsyncSession) -> None:
        """Delete an action category with FK guard.

        Explicit count query before DELETE.
        Raises CategoryInUseError if referenced by ClassificationResult or ClassificationFeedback.
        """
        category = await self.get_action_category(category_id, db)

        # Check ClassificationResult references
        cr_count_result = await db.execute(
            select(func.count(ClassificationResult.id)).where(
                ClassificationResult.action_category_id == category_id
            )
        )
        cr_count: int = cr_count_result.scalar_one() or 0

        # Check ClassificationFeedback references (original or corrected)
        fb_count_result = await db.execute(
            select(func.count(ClassificationFeedback.id)).where(
                (ClassificationFeedback.original_action_id == category_id)
                | (ClassificationFeedback.corrected_action_id == category_id)
            )
        )
        fb_count: int = fb_count_result.scalar_one() or 0

        affected = cr_count + fb_count
        if affected > 0:
            raise CategoryInUseError(category_id=category_id, affected_email_count=affected)

        await db.delete(category)
        logger.info("action_category_deleted", category_id=str(category_id))

    async def reorder_action_categories(
        self,
        ordered_ids: list[uuid.UUID],
        db: AsyncSession,
    ) -> list[ActionCategory]:
        """Bulk reorder action categories. ordered_ids[0] gets display_order 0."""
        result = await db.execute(select(ActionCategory).where(ActionCategory.id.in_(ordered_ids)))
        found = {c.id: c for c in result.scalars().all()}

        missing = [rid for rid in ordered_ids if rid not in found]
        if missing:
            raise NotFoundError(
                f"Action category(s) not found: {', '.join(str(i) for i in missing)}"
            )

        for idx, cid in enumerate(ordered_ids):
            found[cid].display_order = idx

        await db.flush()
        return [found[cid] for cid in ordered_ids]

    # --- TypeCategory (same pattern) ---

    async def list_type_categories(self, db: AsyncSession) -> list[TypeCategory]:
        """List all type categories ordered by display_order."""
        result = await db.execute(select(TypeCategory).order_by(TypeCategory.display_order.asc()))
        return list(result.scalars().all())

    async def get_type_category(self, category_id: uuid.UUID, db: AsyncSession) -> TypeCategory:
        """Get a single type category. Raises NotFoundError if missing."""
        result = await db.execute(select(TypeCategory).where(TypeCategory.id == category_id))
        category = result.scalar_one_or_none()
        if category is None:
            raise NotFoundError(f"Type category {category_id} not found")
        return category

    async def create_type_category(
        self,
        slug: str,
        name: str,
        description: str,
        is_fallback: bool,
        is_active: bool,
        db: AsyncSession,
    ) -> TypeCategory:
        """Create a type category. Raises DuplicateResourceError if slug exists."""
        existing = await db.execute(select(TypeCategory).where(TypeCategory.slug == slug))
        if existing.scalar_one_or_none() is not None:
            raise DuplicateResourceError(f"Type category slug '{slug}' already exists")

        max_result = await db.execute(select(func.max(TypeCategory.display_order)))
        max_order: int | None = max_result.scalar_one_or_none()
        next_order = (max_order or 0) + 1

        category = TypeCategory(
            id=uuid.uuid4(),
            slug=slug,
            name=name,
            description=description,
            is_fallback=is_fallback,
            is_active=is_active,
            display_order=next_order,
        )
        db.add(category)
        await db.flush()
        await db.refresh(category)
        logger.info("type_category_created", category_id=str(category.id), slug=slug)
        return category

    async def update_type_category(
        self,
        category_id: uuid.UUID,
        db: AsyncSession,
        *,
        name: str | None = None,
        description: str | None = None,
        is_fallback: bool | None = None,
        is_active: bool | None = None,
    ) -> TypeCategory:
        """Partial update of a type category. Slug is immutable."""
        category = await self.get_type_category(category_id, db)
        if name is not None:
            category.name = name
        if description is not None:
            category.description = description
        if is_fallback is not None:
            category.is_fallback = is_fallback
        if is_active is not None:
            category.is_active = is_active
        await db.flush()
        await db.refresh(category)
        logger.info("type_category_updated", category_id=str(category_id))
        return category

    async def delete_type_category(self, category_id: uuid.UUID, db: AsyncSession) -> None:
        """Delete a type category with FK guard.

        Explicit count query before DELETE.
        Raises CategoryInUseError if referenced by ClassificationResult or ClassificationFeedback.
        """
        category = await self.get_type_category(category_id, db)

        cr_count_result = await db.execute(
            select(func.count(ClassificationResult.id)).where(
                ClassificationResult.type_category_id == category_id
            )
        )
        cr_count: int = cr_count_result.scalar_one() or 0

        fb_count_result = await db.execute(
            select(func.count(ClassificationFeedback.id)).where(
                (ClassificationFeedback.original_type_id == category_id)
                | (ClassificationFeedback.corrected_type_id == category_id)
            )
        )
        fb_count: int = fb_count_result.scalar_one() or 0

        affected = cr_count + fb_count
        if affected > 0:
            raise CategoryInUseError(category_id=category_id, affected_email_count=affected)

        await db.delete(category)
        logger.info("type_category_deleted", category_id=str(category_id))

    async def reorder_type_categories(
        self,
        ordered_ids: list[uuid.UUID],
        db: AsyncSession,
    ) -> list[TypeCategory]:
        """Bulk reorder type categories. ordered_ids[0] gets display_order 0."""
        result = await db.execute(select(TypeCategory).where(TypeCategory.id.in_(ordered_ids)))
        found = {c.id: c for c in result.scalars().all()}

        missing = [rid for rid in ordered_ids if rid not in found]
        if missing:
            raise NotFoundError(f"Type category(s) not found: {', '.join(str(i) for i in missing)}")

        for idx, cid in enumerate(ordered_ids):
            found[cid].display_order = idx

        await db.flush()
        return [found[cid] for cid in ordered_ids]
