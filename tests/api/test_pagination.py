"""Tests for pagination parameter validation on GET /api/v1/emails/.

Scope: PaginationParams validation (page/page_size bounds) and
PaginatedResponse shape. DB is mocked — no real PostgreSQL.

The emails list endpoint makes exactly 2 db.execute calls when the
email list is empty:
  1. COUNT query (total)
  2. Paginated SELECT (items)
"""

from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient


def _make_empty_db_execute(mock_db: AsyncMock, total: int = 0) -> None:
    """Configure mock_db.execute to return an empty email list with given total."""
    count_result = MagicMock()
    count_result.scalar_one.return_value = total

    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [count_result, scalars_result]


class TestPaginationParamValidation:
    """PaginationParams: enforce page>=1 and 1<=page_size<=100 at the API boundary."""

    async def test_page_zero_is_rejected(self, admin_client: AsyncClient) -> None:
        """page=0 violates ge=1 constraint — FastAPI returns 422."""
        response = await admin_client.get("/api/v1/emails/?page=0")
        assert response.status_code == 422

    async def test_page_negative_is_rejected(self, admin_client: AsyncClient) -> None:
        """page=-1 violates ge=1 constraint — FastAPI returns 422."""
        response = await admin_client.get("/api/v1/emails/?page=-1")
        assert response.status_code == 422

    async def test_page_size_zero_is_rejected(self, admin_client: AsyncClient) -> None:
        """page_size=0 violates ge=1 constraint — FastAPI returns 422."""
        response = await admin_client.get("/api/v1/emails/?page_size=0")
        assert response.status_code == 422

    async def test_page_size_negative_is_rejected(self, admin_client: AsyncClient) -> None:
        """page_size=-5 violates ge=1 constraint — FastAPI returns 422."""
        response = await admin_client.get("/api/v1/emails/?page_size=-5")
        assert response.status_code == 422

    async def test_page_size_over_100_is_rejected(self, admin_client: AsyncClient) -> None:
        """page_size=101 violates le=100 constraint — FastAPI returns 422."""
        response = await admin_client.get("/api/v1/emails/?page_size=101")
        assert response.status_code == 422

    async def test_page_size_100_is_accepted(
        self, admin_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """page_size=100 is the maximum valid boundary — request succeeds."""
        _make_empty_db_execute(mock_db, total=0)
        response = await admin_client.get("/api/v1/emails/?page_size=100")
        assert response.status_code == 200

    async def test_page_size_1_is_accepted(
        self, admin_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """page_size=1 is the minimum valid boundary — request succeeds."""
        _make_empty_db_execute(mock_db, total=0)
        response = await admin_client.get("/api/v1/emails/?page_size=1")
        assert response.status_code == 200

    async def test_page_1_is_accepted(self, admin_client: AsyncClient, mock_db: AsyncMock) -> None:
        """page=1 is the minimum valid value — request succeeds."""
        _make_empty_db_execute(mock_db, total=0)
        response = await admin_client.get("/api/v1/emails/?page=1")
        assert response.status_code == 200


class TestPaginatedResponseShape:
    """PaginatedResponse[EmailListItem] shape and field values."""

    async def test_default_pagination_fields(
        self, admin_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """Default request uses page=1, page_size=20. Response echoes these values."""
        _make_empty_db_execute(mock_db, total=0)
        response = await admin_client.get("/api/v1/emails/")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 20

    async def test_paginated_response_required_fields(
        self, admin_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """Response includes all required PaginatedResponse fields."""
        _make_empty_db_execute(mock_db, total=0)
        response = await admin_client.get("/api/v1/emails/")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "pages" in data

    async def test_empty_result_has_zero_total_and_pages(
        self, admin_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """No emails in DB: total=0, pages=0, items=[]."""
        _make_empty_db_execute(mock_db, total=0)
        response = await admin_client.get("/api/v1/emails/")
        data = response.json()
        assert data["total"] == 0
        assert data["pages"] == 0
        assert data["items"] == []

    async def test_pages_calculation_ceil_division(
        self, admin_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """pages = ceil(total / page_size). 12 items / page_size=5 = 3 pages."""
        _make_empty_db_execute(mock_db, total=12)
        response = await admin_client.get("/api/v1/emails/?page_size=5")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 12
        assert data["pages"] == 3  # ceil(12 / 5) = 3

    async def test_pages_calculation_exact_division(
        self, admin_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """10 items / page_size=5 = 2 pages (exact, no ceiling effect)."""
        _make_empty_db_execute(mock_db, total=10)
        response = await admin_client.get("/api/v1/emails/?page_size=5")
        data = response.json()
        assert data["pages"] == 2  # 10 / 5 = 2

    async def test_pages_calculation_single_item(
        self, admin_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """1 item / page_size=20 = 1 page."""
        _make_empty_db_execute(mock_db, total=1)
        response = await admin_client.get("/api/v1/emails/?page_size=20")
        data = response.json()
        assert data["pages"] == 1

    async def test_page_beyond_total_returns_empty_items(
        self, admin_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """Requesting page 999 with only 5 total items returns empty items list.

        The DB mock returns [] for the page query. Total and pages remain accurate.
        """
        _make_empty_db_execute(mock_db, total=5)
        response = await admin_client.get("/api/v1/emails/?page=999&page_size=20")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 5
        assert data["pages"] == 1  # ceil(5 / 20) = 1

    async def test_custom_page_and_page_size_echoed_in_response(
        self, admin_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """page and page_size query params are echoed back in the response."""
        _make_empty_db_execute(mock_db, total=0)
        response = await admin_client.get("/api/v1/emails/?page=3&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 3
        assert data["page_size"] == 10


class TestEmailsListAuth:
    """GET /api/v1/emails/ — authentication and authorization enforcement."""

    async def test_unauthenticated_returns_401(self, unauthenticated_client: AsyncClient) -> None:
        """Email list requires authentication — no token returns 401."""
        response = await unauthenticated_client.get("/api/v1/emails/")
        assert response.status_code == 401

    async def test_reviewer_can_access_email_list(
        self, reviewer_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """Reviewer role is authorized to list emails (require_reviewer_or_admin)."""
        _make_empty_db_execute(mock_db, total=0)
        response = await reviewer_client.get("/api/v1/emails/")
        assert response.status_code == 200

    async def test_admin_can_access_email_list(
        self, admin_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """Admin role is authorized to list emails."""
        _make_empty_db_execute(mock_db, total=0)
        response = await admin_client.get("/api/v1/emails/")
        assert response.status_code == 200
