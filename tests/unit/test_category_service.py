"""Tests for CategoryService — mocked AsyncSession.

Coverage targets (ActionCategory):
  1. list_action_categories: returns ordered list
  2. get_action_category: found → returns category
  3. get_action_category: not found → raises NotFoundError
  4. create_action_category: new slug → category created and returned
  5. create_action_category: duplicate slug → raises DuplicateResourceError
  6. update_action_category: partial update applies only provided fields
  7. delete_action_category: no references → calls db.delete
  8. delete_action_category: has ClassificationResult references → raises CategoryInUseError
  9. reorder_action_categories: all IDs found → assigns sequential display_order
 10. reorder_action_categories: missing ID → raises NotFoundError

Coverage targets (TypeCategory — mirrors ActionCategory):
 11. list_type_categories: returns list
 12. get_type_category: not found → raises NotFoundError
 13. create_type_category: duplicate slug → raises DuplicateResourceError
 14. update_type_category: partial update
 15. delete_type_category: feedback reference raises CategoryInUseError
 16. reorder_type_categories: missing ID → raises NotFoundError

Mocking strategy:
  - db: AsyncMock with execute configured per test via side_effect list.
  - Category objects: MagicMock() — avoid SQLAlchemy ORM constructor.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import CategoryInUseError, DuplicateResourceError, NotFoundError
from src.services.category_service import CategoryService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _scalar_result(value: object) -> MagicMock:
    """Result whose scalar_one_or_none() returns value."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    r.scalar_one.return_value = value
    return r


def _scalars_result(items: list[object]) -> MagicMock:
    """Result whose scalars().all() returns items."""
    r = MagicMock()
    inner = MagicMock()
    inner.all.return_value = items
    r.scalars.return_value = inner
    return r


def _make_action_category(
    category_id: uuid.UUID | None = None,
    slug: str = "respond",
    display_order: int = 0,
) -> MagicMock:
    cat = MagicMock()
    cat.id = category_id or uuid.uuid4()
    cat.slug = slug
    cat.display_order = display_order
    return cat


def _make_type_category(
    category_id: uuid.UUID | None = None,
    slug: str = "support",
    display_order: int = 0,
) -> MagicMock:
    cat = MagicMock()
    cat.id = category_id or uuid.uuid4()
    cat.slug = slug
    cat.display_order = display_order
    return cat


# ---------------------------------------------------------------------------
# TestListActionCategories
# ---------------------------------------------------------------------------


class TestListActionCategories:
    async def test_returns_list_in_order(self) -> None:
        db = _make_db()
        service = CategoryService()
        cats = [_make_action_category(display_order=i) for i in range(3)]
        db.execute.return_value = _scalars_result(cats)

        result = await service.list_action_categories(db)

        assert len(result) == 3


# ---------------------------------------------------------------------------
# TestGetActionCategory
# ---------------------------------------------------------------------------


class TestGetActionCategory:
    async def test_found_returns_category(self) -> None:
        db = _make_db()
        service = CategoryService()
        cat = _make_action_category()
        db.execute.return_value = _scalar_result(cat)

        result = await service.get_action_category(cat.id, db)

        assert result is cat

    async def test_not_found_raises_not_found_error(self) -> None:
        db = _make_db()
        service = CategoryService()
        db.execute.return_value = _scalar_result(None)

        with pytest.raises(NotFoundError, match="Action category"):
            await service.get_action_category(uuid.uuid4(), db)


# ---------------------------------------------------------------------------
# TestCreateActionCategory
# ---------------------------------------------------------------------------


class TestCreateActionCategory:
    async def test_new_slug_creates_category(self) -> None:
        db = _make_db()
        service = CategoryService()
        new_id = uuid.uuid4()

        # 1st execute: slug check → None (no existing)
        # 2nd execute: MAX display_order → 5
        db.execute.side_effect = [
            _scalar_result(None),
            _scalar_result(5),
        ]

        with patch("src.services.category_service.uuid") as mock_uuid:
            mock_uuid.uuid4.return_value = new_id

            await service.create_action_category(
                slug="archive",
                name="Archive",
                description="Archive emails",
                is_fallback=False,
                is_active=True,
                db=db,
            )

        db.add.assert_called_once()
        db.flush.assert_awaited_once()
        db.refresh.assert_awaited_once()

    async def test_duplicate_slug_raises_duplicate_resource_error(self) -> None:
        db = _make_db()
        service = CategoryService()
        existing = _make_action_category(slug="respond")
        db.execute.return_value = _scalar_result(existing)

        with pytest.raises(DuplicateResourceError, match="respond"):
            await service.create_action_category(
                slug="respond",
                name="Respond",
                description="",
                is_fallback=False,
                is_active=True,
                db=db,
            )

    async def test_max_order_none_uses_one(self) -> None:
        """When no categories exist, MAX returns None → next_order = 1."""
        db = _make_db()
        service = CategoryService()

        db.execute.side_effect = [
            _scalar_result(None),  # slug check
            _scalar_result(None),  # max display_order
        ]

        await service.create_action_category(
            slug="new",
            name="New",
            description="",
            is_fallback=False,
            is_active=True,
            db=db,
        )

        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        assert added.display_order == 1


# ---------------------------------------------------------------------------
# TestUpdateActionCategory
# ---------------------------------------------------------------------------


class TestUpdateActionCategory:
    async def test_partial_update_only_modifies_provided_fields(self) -> None:
        db = _make_db()
        service = CategoryService()
        cat = _make_action_category()
        cat.name = "Old Name"
        cat.description = "Old Desc"
        db.execute.return_value = _scalar_result(cat)

        await service.update_action_category(
            cat.id,
            db,
            name="New Name",
        )

        assert cat.name == "New Name"
        # description not changed
        assert cat.description == "Old Desc"
        db.flush.assert_awaited_once()

    async def test_update_all_fields(self) -> None:
        db = _make_db()
        service = CategoryService()
        cat = _make_action_category()
        db.execute.return_value = _scalar_result(cat)

        await service.update_action_category(
            cat.id,
            db,
            name="Updated",
            description="New desc",
            is_fallback=True,
            is_active=False,
        )

        assert cat.name == "Updated"
        assert cat.description == "New desc"
        assert cat.is_fallback is True
        assert cat.is_active is False


# ---------------------------------------------------------------------------
# TestDeleteActionCategory
# ---------------------------------------------------------------------------


class TestDeleteActionCategory:
    async def test_no_references_deletes_category(self) -> None:
        db = _make_db()
        service = CategoryService()
        cat = _make_action_category()

        # get_action_category, cr_count=0, fb_count=0
        db.execute.side_effect = [
            _scalar_result(cat),
            _scalar_result(0),
            _scalar_result(0),
        ]

        await service.delete_action_category(cat.id, db)

        db.delete.assert_awaited_once_with(cat)

    async def test_classification_result_reference_raises_category_in_use(self) -> None:
        db = _make_db()
        service = CategoryService()
        cat = _make_action_category()

        db.execute.side_effect = [
            _scalar_result(cat),
            _scalar_result(3),  # cr_count = 3
            _scalar_result(0),
        ]

        with pytest.raises(CategoryInUseError) as exc_info:
            await service.delete_action_category(cat.id, db)

        assert exc_info.value.affected_email_count == 3
        db.delete.assert_not_awaited()

    async def test_feedback_reference_raises_category_in_use(self) -> None:
        db = _make_db()
        service = CategoryService()
        cat = _make_action_category()

        db.execute.side_effect = [
            _scalar_result(cat),
            _scalar_result(0),  # cr_count
            _scalar_result(2),  # fb_count = 2
        ]

        with pytest.raises(CategoryInUseError) as exc_info:
            await service.delete_action_category(cat.id, db)

        assert exc_info.value.affected_email_count == 2


# ---------------------------------------------------------------------------
# TestReorderActionCategories
# ---------------------------------------------------------------------------


class TestReorderActionCategories:
    async def test_assigns_sequential_display_order(self) -> None:
        db = _make_db()
        service = CategoryService()

        id_a = uuid.uuid4()
        id_b = uuid.uuid4()
        cat_a = _make_action_category(category_id=id_a, display_order=5)
        cat_b = _make_action_category(category_id=id_b, display_order=3)

        db.execute.return_value = _scalars_result([cat_a, cat_b])

        result = await service.reorder_action_categories([id_a, id_b], db)

        assert cat_a.display_order == 0
        assert cat_b.display_order == 1
        assert len(result) == 2
        db.flush.assert_awaited_once()

    async def test_missing_id_raises_not_found_error(self) -> None:
        db = _make_db()
        service = CategoryService()
        existing_id = uuid.uuid4()
        missing_id = uuid.uuid4()

        cat = _make_action_category(category_id=existing_id)
        db.execute.return_value = _scalars_result([cat])  # only one found

        with pytest.raises(NotFoundError, match="not found"):
            await service.reorder_action_categories([existing_id, missing_id], db)


# ---------------------------------------------------------------------------
# TestListTypeCategories
# ---------------------------------------------------------------------------


class TestListTypeCategories:
    async def test_returns_list(self) -> None:
        db = _make_db()
        service = CategoryService()
        cats = [_make_type_category(display_order=i) for i in range(2)]
        db.execute.return_value = _scalars_result(cats)

        result = await service.list_type_categories(db)

        assert len(result) == 2


# ---------------------------------------------------------------------------
# TestGetTypeCategory
# ---------------------------------------------------------------------------


class TestGetTypeCategory:
    async def test_not_found_raises_not_found_error(self) -> None:
        db = _make_db()
        service = CategoryService()
        db.execute.return_value = _scalar_result(None)

        with pytest.raises(NotFoundError, match="Type category"):
            await service.get_type_category(uuid.uuid4(), db)


# ---------------------------------------------------------------------------
# TestCreateTypeCategory
# ---------------------------------------------------------------------------


class TestCreateTypeCategory:
    async def test_duplicate_slug_raises_duplicate_resource_error(self) -> None:
        db = _make_db()
        service = CategoryService()
        existing = _make_type_category(slug="support")
        db.execute.return_value = _scalar_result(existing)

        with pytest.raises(DuplicateResourceError, match="support"):
            await service.create_type_category(
                slug="support",
                name="Support",
                description="",
                is_fallback=False,
                is_active=True,
                db=db,
            )


# ---------------------------------------------------------------------------
# TestUpdateTypeCategory
# ---------------------------------------------------------------------------


class TestUpdateTypeCategory:
    async def test_partial_update_modifies_only_provided_fields(self) -> None:
        db = _make_db()
        service = CategoryService()
        cat = _make_type_category()
        cat.name = "Old"
        cat.description = "Old Desc"
        db.execute.return_value = _scalar_result(cat)

        await service.update_type_category(cat.id, db, name="New")

        assert cat.name == "New"
        assert cat.description == "Old Desc"

    async def test_is_active_false_updates(self) -> None:
        db = _make_db()
        service = CategoryService()
        cat = _make_type_category()
        cat.is_active = True
        db.execute.return_value = _scalar_result(cat)

        await service.update_type_category(cat.id, db, is_active=False)

        assert cat.is_active is False


# ---------------------------------------------------------------------------
# TestDeleteTypeCategory
# ---------------------------------------------------------------------------


class TestDeleteTypeCategory:
    async def test_no_references_deletes_type_category(self) -> None:
        db = _make_db()
        service = CategoryService()
        cat = _make_type_category()

        db.execute.side_effect = [
            _scalar_result(cat),
            _scalar_result(0),
            _scalar_result(0),
        ]

        await service.delete_type_category(cat.id, db)

        db.delete.assert_awaited_once_with(cat)

    async def test_feedback_reference_raises_category_in_use(self) -> None:
        db = _make_db()
        service = CategoryService()
        cat = _make_type_category()

        db.execute.side_effect = [
            _scalar_result(cat),
            _scalar_result(0),
            _scalar_result(4),  # fb_count
        ]

        with pytest.raises(CategoryInUseError) as exc_info:
            await service.delete_type_category(cat.id, db)

        assert exc_info.value.affected_email_count == 4


# ---------------------------------------------------------------------------
# TestReorderTypeCategories
# ---------------------------------------------------------------------------


class TestReorderTypeCategories:
    async def test_assigns_sequential_display_order(self) -> None:
        db = _make_db()
        service = CategoryService()
        id_a = uuid.uuid4()
        id_b = uuid.uuid4()
        cat_a = _make_type_category(category_id=id_a)
        cat_b = _make_type_category(category_id=id_b)
        db.execute.return_value = _scalars_result([cat_a, cat_b])

        await service.reorder_type_categories([id_a, id_b], db)

        assert cat_a.display_order == 0
        assert cat_b.display_order == 1

    async def test_missing_id_raises_not_found_error(self) -> None:
        db = _make_db()
        service = CategoryService()
        existing_id = uuid.uuid4()
        missing_id = uuid.uuid4()
        cat = _make_type_category(category_id=existing_id)
        db.execute.return_value = _scalars_result([cat])

        with pytest.raises(NotFoundError):
            await service.reorder_type_categories([existing_id, missing_id], db)
