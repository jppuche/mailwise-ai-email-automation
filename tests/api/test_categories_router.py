"""Unit tests for /api/v1/categories/* and /api/v1/classification/* endpoints.

Covers:
  - categories_router: ActionCategory and TypeCategory CRUD + reorder
  - classification_router: FewShotExample CRUD + ClassificationFeedback list

Pattern:
  - dependency_overrides for auth + mock DB (no real DB or Redis)
  - CategoryService methods mocked via patch on module-level singleton
  - FewShotExample and Feedback endpoints mock db.execute directly (no service)
  - Tests document observable HTTP behaviour, not router internals

try-except D8: assertions (conditionals) only — no try/except in test bodies.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

from src.models.category import ActionCategory, TypeCategory
from src.models.few_shot import FewShotExample

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 1, 1, tzinfo=UTC)
_CAT_ID = uuid.uuid4()
_EX_ID = uuid.uuid4()
_EMAIL_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()


def _make_mock_action_category(
    cat_id: uuid.UUID | None = None,
    slug: str = "respond",
    name: str = "Respond",
    display_order: int = 1,
) -> MagicMock:
    """Build a MagicMock ActionCategory ORM object."""
    cat = MagicMock(spec=ActionCategory)
    cat.id = cat_id or uuid.uuid4()
    cat.slug = slug
    cat.name = name
    cat.description = "A test action category"
    cat.is_fallback = False
    cat.is_active = True
    cat.display_order = display_order
    cat.created_at = _NOW
    cat.updated_at = _NOW
    return cat


def _make_mock_type_category(
    cat_id: uuid.UUID | None = None,
    slug: str = "inquiry",
    name: str = "Inquiry",
    display_order: int = 1,
) -> MagicMock:
    """Build a MagicMock TypeCategory ORM object."""
    cat = MagicMock(spec=TypeCategory)
    cat.id = cat_id or uuid.uuid4()
    cat.slug = slug
    cat.name = name
    cat.description = "A test type category"
    cat.is_fallback = False
    cat.is_active = True
    cat.display_order = display_order
    cat.created_at = _NOW
    cat.updated_at = _NOW
    return cat


def _make_mock_example(
    ex_id: uuid.UUID | None = None,
    action_slug: str = "respond",
    type_slug: str = "inquiry",
) -> MagicMock:
    """Build a MagicMock FewShotExample ORM object."""
    ex = MagicMock(spec=FewShotExample)
    ex.id = ex_id or uuid.uuid4()
    ex.email_snippet = "Please help me with my order."
    ex.action_slug = action_slug
    ex.type_slug = type_slug
    ex.rationale = "Customer requesting assistance."
    ex.is_active = True
    ex.created_at = _NOW
    ex.updated_at = _NOW
    return ex


def _scalar_result(obj: object) -> MagicMock:
    """Mock execute-result: scalar_one_or_none() returns obj."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    return result


def _scalars_all_result(items: list[object]) -> MagicMock:
    """Mock execute-result: scalars().all() returns items."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    result.scalars.return_value = scalars_mock
    return result


def _scalar_one_result(value: object) -> MagicMock:
    """Mock execute-result: scalar_one() returns value."""
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


async def _refresh_timestamps(obj: object) -> None:
    """Side effect for db.refresh: stamps created_at/updated_at."""
    obj.created_at = _NOW  # type: ignore[attr-defined]
    obj.updated_at = _NOW  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# TestListActionCategories
# ---------------------------------------------------------------------------


class TestListActionCategories:
    """GET /api/v1/categories/actions — list all action categories."""

    async def test_admin_gets_200_with_categories(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Admin retrieves a non-empty list of action categories."""
        cat = _make_mock_action_category(slug="respond", name="Respond")
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.list_action_categories = AsyncMock(return_value=[cat])
            response = await admin_client.get("/api/v1/categories/actions")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["slug"] == "respond"
        assert body[0]["name"] == "Respond"
        assert "id" in body[0]
        assert "display_order" in body[0]

    async def test_reviewer_gets_200(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer role is allowed to list action categories."""
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.list_action_categories = AsyncMock(return_value=[])
            response = await reviewer_client.get("/api/v1/categories/actions")

        assert response.status_code == 200
        assert response.json() == []

    async def test_unauthenticated_gets_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """Missing auth token returns 401."""
        response = await unauthenticated_client.get("/api/v1/categories/actions")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# TestCreateActionCategory
# ---------------------------------------------------------------------------


class TestCreateActionCategory:
    """POST /api/v1/categories/actions — create action category (Admin, 201)."""

    async def test_admin_creates_category_gets_201(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Admin creates an action category and receives 201 with the new resource."""
        cat = _make_mock_action_category(slug="archive", name="Archive")
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.create_action_category = AsyncMock(return_value=cat)
            response = await admin_client.post(
                "/api/v1/categories/actions",
                json={
                    "slug": "archive",
                    "name": "Archive",
                    "description": "",
                    "is_fallback": False,
                },
            )

        assert response.status_code == 201
        body = response.json()
        assert body["slug"] == "archive"
        assert body["name"] == "Archive"
        assert "id" in body

    async def test_reviewer_cannot_create_category(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer role cannot create action categories."""
        response = await reviewer_client.post(
            "/api/v1/categories/actions",
            json={"slug": "archive", "name": "Archive"},
        )
        assert response.status_code == 403

    async def test_duplicate_slug_gets_409(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Duplicate slug raises DuplicateResourceError → 409 Conflict."""
        from src.core.exceptions import DuplicateResourceError

        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.create_action_category = AsyncMock(
                side_effect=DuplicateResourceError("slug 'respond' already exists")
            )
            response = await admin_client.post(
                "/api/v1/categories/actions",
                json={"slug": "respond", "name": "Respond"},
            )

        assert response.status_code == 409

    async def test_missing_name_gets_422(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Missing required 'name' field returns 422 Unprocessable Entity."""
        response = await admin_client.post(
            "/api/v1/categories/actions",
            json={"slug": "archive"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestGetActionCategory
# ---------------------------------------------------------------------------


class TestGetActionCategory:
    """GET /api/v1/categories/actions/{id} — single action category."""

    async def test_admin_gets_single_category(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Admin fetches an existing action category by UUID."""
        cat_id = uuid.uuid4()
        cat = _make_mock_action_category(cat_id=cat_id, slug="urgent", name="Urgent")
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.get_action_category = AsyncMock(return_value=cat)
            response = await admin_client.get(f"/api/v1/categories/actions/{cat_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(cat_id)
        assert body["slug"] == "urgent"

    async def test_not_found_gets_404(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Non-existent category ID returns 404."""
        from src.core.exceptions import NotFoundError

        missing_id = uuid.uuid4()
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.get_action_category = AsyncMock(
                side_effect=NotFoundError(f"Action category {missing_id} not found")
            )
            response = await admin_client.get(f"/api/v1/categories/actions/{missing_id}")

        assert response.status_code == 404

    async def test_reviewer_gets_200(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer can fetch a single action category (read access)."""
        cat = _make_mock_action_category()
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.get_action_category = AsyncMock(return_value=cat)
            response = await reviewer_client.get(f"/api/v1/categories/actions/{cat.id}")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# TestUpdateActionCategory
# ---------------------------------------------------------------------------


class TestUpdateActionCategory:
    """PUT /api/v1/categories/actions/{id} — partial update (Admin)."""

    async def test_admin_partial_update_gets_200(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Admin performs a partial update on name."""
        cat_id = uuid.uuid4()
        cat = _make_mock_action_category(cat_id=cat_id, name="Updated Name")
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.update_action_category = AsyncMock(return_value=cat)
            response = await admin_client.put(
                f"/api/v1/categories/actions/{cat_id}",
                json={"name": "Updated Name"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(cat_id)
        assert body["name"] == "Updated Name"

    async def test_reviewer_cannot_update(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer cannot update action categories."""
        response = await reviewer_client.put(
            f"/api/v1/categories/actions/{uuid.uuid4()}",
            json={"name": "Not Allowed"},
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# TestDeleteActionCategory
# ---------------------------------------------------------------------------


class TestDeleteActionCategory:
    """DELETE /api/v1/categories/actions/{id} — delete with FK guard (Admin, 204)."""

    async def test_admin_deletes_category_gets_204(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Admin deletes a category not referenced by any classification → 204."""
        cat_id = uuid.uuid4()
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.delete_action_category = AsyncMock(return_value=None)
            response = await admin_client.delete(f"/api/v1/categories/actions/{cat_id}")

        assert response.status_code == 204
        assert response.content == b""

    async def test_category_in_use_gets_409_with_count(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Deleting a category referenced by 5 emails raises CategoryInUseError → 409."""
        from src.core.exceptions import CategoryInUseError

        cat_id = uuid.uuid4()
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.delete_action_category = AsyncMock(
                side_effect=CategoryInUseError(category_id=cat_id, affected_email_count=5)
            )
            response = await admin_client.delete(f"/api/v1/categories/actions/{cat_id}")

        assert response.status_code == 409
        body = response.json()
        assert body["affected_email_count"] == 5
        assert "category_in_use" in body["error"]

    async def test_reviewer_cannot_delete(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer cannot delete action categories."""
        response = await reviewer_client.delete(f"/api/v1/categories/actions/{uuid.uuid4()}")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# TestReorderActionCategories
# ---------------------------------------------------------------------------


class TestReorderActionCategories:
    """PUT /api/v1/categories/actions/reorder — bulk reorder (Admin)."""

    async def test_admin_reorders_categories_gets_200(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Admin reorders two categories; response reflects new display_order."""
        id_a = uuid.uuid4()
        id_b = uuid.uuid4()
        cat_a = _make_mock_action_category(
            cat_id=id_a, slug="archive", name="Archive", display_order=0
        )
        cat_b = _make_mock_action_category(
            cat_id=id_b, slug="respond", name="Respond", display_order=1
        )
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.reorder_action_categories = AsyncMock(return_value=[cat_a, cat_b])
            payload = {"ordered_ids": [str(id_a), str(id_b)]}
            response = await admin_client.put("/api/v1/categories/actions/reorder", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 2
        assert body[0]["id"] == str(id_a)
        assert body[1]["id"] == str(id_b)

    async def test_missing_id_in_reorder_gets_404(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Reorder with an unknown category ID returns 404."""
        from src.core.exceptions import NotFoundError

        unknown_id = uuid.uuid4()
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.reorder_action_categories = AsyncMock(
                side_effect=NotFoundError(f"Action category(s) not found: {unknown_id}")
            )
            payload = {"ordered_ids": [str(unknown_id)]}
            response = await admin_client.put("/api/v1/categories/actions/reorder", json=payload)

        assert response.status_code == 404

    async def test_empty_ordered_ids_gets_422(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Empty ordered_ids list fails the ReorderRequest validator → 422."""
        response = await admin_client.put(
            "/api/v1/categories/actions/reorder",
            json={"ordered_ids": []},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestListTypeCategories
# ---------------------------------------------------------------------------


class TestListTypeCategories:
    """GET /api/v1/categories/types — list all type categories."""

    async def test_admin_gets_200_with_categories(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Admin retrieves a list of type categories."""
        cat = _make_mock_type_category(slug="inquiry", name="Inquiry")
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.list_type_categories = AsyncMock(return_value=[cat])
            response = await admin_client.get("/api/v1/categories/types")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["slug"] == "inquiry"

    async def test_reviewer_gets_200(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer role can list type categories."""
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.list_type_categories = AsyncMock(return_value=[])
            response = await reviewer_client.get("/api/v1/categories/types")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# TestCreateTypeCategory
# ---------------------------------------------------------------------------


class TestCreateTypeCategory:
    """POST /api/v1/categories/types — create type category (Admin, 201)."""

    async def test_admin_creates_type_category_gets_201(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Admin creates a type category and receives 201."""
        cat = _make_mock_type_category(slug="billing", name="Billing")
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.create_type_category = AsyncMock(return_value=cat)
            response = await admin_client.post(
                "/api/v1/categories/types",
                json={"slug": "billing", "name": "Billing"},
            )

        assert response.status_code == 201
        body = response.json()
        assert body["slug"] == "billing"

    async def test_reviewer_cannot_create_type_category(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer cannot create type categories."""
        response = await reviewer_client.post(
            "/api/v1/categories/types",
            json={"slug": "billing", "name": "Billing"},
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# TestGetTypeCategory
# ---------------------------------------------------------------------------


class TestGetTypeCategory:
    """GET /api/v1/categories/types/{id} — single type category."""

    async def test_admin_gets_single_type_category(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Admin fetches an existing type category by UUID."""
        cat_id = uuid.uuid4()
        cat = _make_mock_type_category(cat_id=cat_id, slug="spam", name="Spam")
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.get_type_category = AsyncMock(return_value=cat)
            response = await admin_client.get(f"/api/v1/categories/types/{cat_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(cat_id)
        assert body["slug"] == "spam"

    async def test_type_category_not_found_gets_404(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Non-existent type category ID returns 404."""
        from src.core.exceptions import NotFoundError

        missing_id = uuid.uuid4()
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.get_type_category = AsyncMock(
                side_effect=NotFoundError(f"Type category {missing_id} not found")
            )
            response = await admin_client.get(f"/api/v1/categories/types/{missing_id}")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# TestUpdateTypeCategory
# ---------------------------------------------------------------------------


class TestUpdateTypeCategory:
    """PUT /api/v1/categories/types/{id} — partial update (Admin)."""

    async def test_admin_partial_update_type_category(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Admin partial-updates a type category name."""
        cat_id = uuid.uuid4()
        cat = _make_mock_type_category(cat_id=cat_id, name="Renamed Type")
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.update_type_category = AsyncMock(return_value=cat)
            response = await admin_client.put(
                f"/api/v1/categories/types/{cat_id}",
                json={"name": "Renamed Type"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Renamed Type"


# ---------------------------------------------------------------------------
# TestDeleteTypeCategory
# ---------------------------------------------------------------------------


class TestDeleteTypeCategory:
    """DELETE /api/v1/categories/types/{id} — delete with FK guard (Admin, 204)."""

    async def test_admin_deletes_type_category_gets_204(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Admin deletes an unreferenced type category → 204."""
        cat_id = uuid.uuid4()
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.delete_type_category = AsyncMock(return_value=None)
            response = await admin_client.delete(f"/api/v1/categories/types/{cat_id}")

        assert response.status_code == 204
        assert response.content == b""

    async def test_type_category_in_use_gets_409_with_count(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Deleting a type category referenced by 3 emails → 409 with affected_email_count."""
        from src.core.exceptions import CategoryInUseError

        cat_id = uuid.uuid4()
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.delete_type_category = AsyncMock(
                side_effect=CategoryInUseError(category_id=cat_id, affected_email_count=3)
            )
            response = await admin_client.delete(f"/api/v1/categories/types/{cat_id}")

        assert response.status_code == 409
        body = response.json()
        assert body["affected_email_count"] == 3

    async def test_reviewer_cannot_delete_type_category(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer cannot delete type categories."""
        response = await reviewer_client.delete(f"/api/v1/categories/types/{uuid.uuid4()}")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# TestReorderTypeCategories
# ---------------------------------------------------------------------------


class TestReorderTypeCategories:
    """PUT /api/v1/categories/types/reorder — bulk reorder (Admin)."""

    async def test_admin_reorders_type_categories(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Admin reorders type categories; response reflects new order."""
        id_a = uuid.uuid4()
        id_b = uuid.uuid4()
        cat_a = _make_mock_type_category(cat_id=id_a, slug="spam", display_order=0)
        cat_b = _make_mock_type_category(cat_id=id_b, slug="inquiry", display_order=1)
        with patch("src.api.routers.categories._category_service") as mock_service:
            mock_service.reorder_type_categories = AsyncMock(return_value=[cat_a, cat_b])
            payload = {"ordered_ids": [str(id_a), str(id_b)]}
            response = await admin_client.put("/api/v1/categories/types/reorder", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert body[0]["id"] == str(id_a)


# ---------------------------------------------------------------------------
# TestListFewShotExamples
# ---------------------------------------------------------------------------


class TestListFewShotExamples:
    """GET /api/v1/classification/examples — list examples (Admin only)."""

    async def test_admin_gets_200_with_examples(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin retrieves a list of few-shot examples."""
        ex = _make_mock_example(ex_id=_EX_ID)
        mock_db.execute.return_value = _scalars_all_result([ex])

        response = await admin_client.get("/api/v1/classification/examples")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["action_slug"] == "respond"
        assert body[0]["type_slug"] == "inquiry"
        assert "id" in body[0]

    async def test_reviewer_cannot_list_examples(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer is not allowed to access few-shot examples."""
        response = await reviewer_client.get("/api/v1/classification/examples")
        assert response.status_code == 403

    async def test_unauthenticated_gets_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """Missing auth returns 401 for examples endpoint."""
        response = await unauthenticated_client.get("/api/v1/classification/examples")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# TestCreateFewShotExample
# ---------------------------------------------------------------------------


class TestCreateFewShotExample:
    """POST /api/v1/classification/examples — create example (Admin, 201)."""

    async def test_admin_creates_example_gets_201(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin creates a few-shot example and receives 201 with the new resource."""
        mock_db.refresh.side_effect = _refresh_timestamps

        payload = {
            "email_snippet": "I need help with my invoice.",
            "action_slug": "respond",
            "type_slug": "billing",
            "rationale": "Customer billing question.",
        }
        response = await admin_client.post("/api/v1/classification/examples", json=payload)

        assert response.status_code == 201
        body = response.json()
        assert body["email_snippet"] == "I need help with my invoice."
        assert body["action_slug"] == "respond"
        assert body["type_slug"] == "billing"
        assert body["rationale"] == "Customer billing question."
        assert body["is_active"] is True
        assert "id" in body

    async def test_reviewer_cannot_create_example(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer cannot create few-shot examples."""
        payload = {
            "email_snippet": "Test snippet",
            "action_slug": "respond",
            "type_slug": "inquiry",
        }
        response = await reviewer_client.post("/api/v1/classification/examples", json=payload)
        assert response.status_code == 403

    async def test_missing_snippet_gets_422(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Missing required email_snippet returns 422."""
        response = await admin_client.post(
            "/api/v1/classification/examples",
            json={"action_slug": "respond", "type_slug": "inquiry"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestUpdateFewShotExample
# ---------------------------------------------------------------------------


class TestUpdateFewShotExample:
    """PUT /api/v1/classification/examples/{id} — partial update (Admin)."""

    async def test_admin_updates_example_gets_200(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin patches is_active on an existing example."""
        ex_id = uuid.uuid4()
        ex = _make_mock_example(ex_id=ex_id)
        mock_db.execute.return_value = _scalar_result(ex)
        mock_db.refresh.return_value = None

        payload = {"is_active": False}
        response = await admin_client.put(f"/api/v1/classification/examples/{ex_id}", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(ex_id)

    async def test_update_missing_example_gets_404(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Updating a non-existent example returns 404."""
        mock_db.execute.return_value = _scalar_result(None)

        response = await admin_client.put(
            f"/api/v1/classification/examples/{uuid.uuid4()}",
            json={"is_active": False},
        )

        assert response.status_code == 404

    async def test_reviewer_cannot_update_example(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer cannot update few-shot examples."""
        response = await reviewer_client.put(
            f"/api/v1/classification/examples/{uuid.uuid4()}",
            json={"is_active": False},
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# TestDeleteFewShotExample
# ---------------------------------------------------------------------------


class TestDeleteFewShotExample:
    """DELETE /api/v1/classification/examples/{id} — delete (Admin, 204)."""

    async def test_admin_deletes_example_gets_204(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin deletes an existing few-shot example → 204."""
        ex_id = uuid.uuid4()
        ex = _make_mock_example(ex_id=ex_id)
        mock_db.execute.return_value = _scalar_result(ex)

        response = await admin_client.delete(f"/api/v1/classification/examples/{ex_id}")

        assert response.status_code == 204
        assert response.content == b""

    async def test_delete_missing_example_gets_404(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Deleting a non-existent example returns 404."""
        mock_db.execute.return_value = _scalar_result(None)

        response = await admin_client.delete(f"/api/v1/classification/examples/{uuid.uuid4()}")

        assert response.status_code == 404

    async def test_reviewer_cannot_delete_example(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer cannot delete few-shot examples."""
        response = await reviewer_client.delete(f"/api/v1/classification/examples/{uuid.uuid4()}")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# TestListFeedback
# ---------------------------------------------------------------------------


class TestListFeedback:
    """GET /api/v1/classification/feedback — paginated feedback (Admin only)."""

    async def test_admin_gets_200_paginated_feedback(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin retrieves paginated feedback list with resolved slugs."""
        fb_id = uuid.uuid4()
        email_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Build a mock Row object with named attributes matching the JOIN columns
        mock_row = MagicMock()
        mock_row.id = fb_id
        mock_row.email_id = email_id
        mock_row.original_action = "respond"
        mock_row.original_type = "inquiry"
        mock_row.corrected_action = "archive"
        mock_row.corrected_type = "spam"
        mock_row.corrected_by = user_id
        mock_row.corrected_at = _NOW

        # First execute: count query → scalar_one()
        # Second execute: paginated JOIN query → result.all()
        count_result = _scalar_one_result(1)
        rows_result = MagicMock()
        rows_result.all.return_value = [mock_row]
        mock_db.execute.side_effect = [count_result, rows_result]

        response = await admin_client.get("/api/v1/classification/feedback")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["page"] == 1
        assert body["page_size"] == 20
        assert body["pages"] == 1
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["id"] == str(fb_id)
        assert item["original_action"] == "respond"
        assert item["corrected_action"] == "archive"
        assert item["original_type"] == "inquiry"
        assert item["corrected_type"] == "spam"

    async def test_feedback_empty_result(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Feedback endpoint with zero records returns total=0, pages=0."""
        count_result = _scalar_one_result(0)
        rows_result = MagicMock()
        rows_result.all.return_value = []
        mock_db.execute.side_effect = [count_result, rows_result]

        response = await admin_client.get("/api/v1/classification/feedback")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 0
        assert body["pages"] == 0
        assert body["items"] == []

    async def test_reviewer_cannot_list_feedback(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer is not allowed to access classification feedback."""
        response = await reviewer_client.get("/api/v1/classification/feedback")
        assert response.status_code == 403

    async def test_unauthenticated_gets_401_for_feedback(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """Missing auth returns 401 for the feedback endpoint."""
        response = await unauthenticated_client.get("/api/v1/classification/feedback")
        assert response.status_code == 401

    async def test_feedback_pagination_params(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Page and page_size query params are reflected in the response."""
        count_result = _scalar_one_result(50)
        rows_result = MagicMock()
        rows_result.all.return_value = []
        mock_db.execute.side_effect = [count_result, rows_result]

        response = await admin_client.get("/api/v1/classification/feedback?page=3&page_size=10")

        assert response.status_code == 200
        body = response.json()
        assert body["page"] == 3
        assert body["page_size"] == 10
        assert body["total"] == 50
        assert body["pages"] == 5
