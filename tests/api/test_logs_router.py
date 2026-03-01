"""Unit tests for GET /api/v1/logs/ endpoint.

Coverage:
  - TestListLogsBasic       — 200 with items, empty list, reviewer forbidden
  - TestListLogsFilters     — level, source, since, email_id, combined
  - TestListLogsPagination  — defaults, custom, max limit, exceeded limit
  - TestListLogsSchema      — context field type enforcement
  - TestListLogsAuth        — unauthenticated 401

Architecture constraints (D8):
  - Tests use assert conditionals — no try/except for response parsing.
  - Mocks follow B08/B09 pattern: MagicMock for ORM models, AsyncMock for DB.
  - count query → scalar_one(); paginated fetch → scalars().all().
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from src.models.system_log import SystemLog

BASE = "/api/v1/logs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_log(
    log_id: uuid.UUID | None = None,
    level: str = "INFO",
    source: str = "classification",
    message: str = "Test log message",
    email_id: uuid.UUID | None = None,
) -> MagicMock:
    """Return a MagicMock SystemLog ORM object."""
    log = MagicMock(spec=SystemLog)
    log.id = log_id or uuid.uuid4()
    log.timestamp = datetime(2024, 1, 1, tzinfo=UTC)
    log.level = level
    log.source = source
    log.message = message
    log.email_id = email_id
    log.context = {"email_id": str(uuid.uuid4())}
    log.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    log.updated_at = datetime(2024, 1, 1, tzinfo=UTC)
    return log


def _scalar_one_result(value: object) -> MagicMock:
    """Wrap a value so result.scalar_one() returns it (COUNT query)."""
    res = MagicMock()
    res.scalar_one.return_value = value
    return res


def _scalars_all_result(items: list[object]) -> MagicMock:
    """Wrap a list so result.scalars().all() returns it (paginated fetch)."""
    res = MagicMock()
    res.scalars.return_value.all.return_value = items
    return res


# ---------------------------------------------------------------------------
# TestListLogsBasic
# ---------------------------------------------------------------------------


class TestListLogsBasic:
    """GET /api/v1/logs/ — basic access and empty list."""

    async def test_list_logs_admin(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin receives 200 with a populated LogListResponse."""
        log1 = _make_mock_log(level="INFO", source="classification")
        log2 = _make_mock_log(level="ERROR", source="routing")
        log3 = _make_mock_log(level="WARNING", source="ingestion")

        mock_db.execute.side_effect = [
            _scalar_one_result(3),
            _scalars_all_result([log1, log2, log3]),
        ]

        resp = await admin_client.get(f"{BASE}/")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3
        assert body["limit"] == 50
        assert body["offset"] == 0

    async def test_list_logs_empty(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """When no logs exist, items is empty and total is 0."""
        mock_db.execute.side_effect = [
            _scalar_one_result(0),
            _scalars_all_result([]),
        ]

        resp = await admin_client.get(f"{BASE}/")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    async def test_list_logs_reviewer_forbidden(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer role is not authorized — 403."""
        resp = await reviewer_client.get(f"{BASE}/")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TestListLogsFilters
# ---------------------------------------------------------------------------


class TestListLogsFilters:
    """GET /api/v1/logs/ — query parameter filters."""

    async def test_list_logs_filter_level(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """level=ERROR returns only ERROR-level log entries."""
        error_log = _make_mock_log(level="ERROR", source="routing")

        mock_db.execute.side_effect = [
            _scalar_one_result(1),
            _scalars_all_result([error_log]),
        ]

        resp = await admin_client.get(f"{BASE}/", params={"level": "ERROR"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["level"] == "ERROR"

    async def test_list_logs_filter_source(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """source=classification filters logs to the classification stage."""
        log = _make_mock_log(level="INFO", source="classification")

        mock_db.execute.side_effect = [
            _scalar_one_result(1),
            _scalars_all_result([log]),
        ]

        resp = await admin_client.get(f"{BASE}/", params={"source": "classification"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["source"] == "classification"

    async def test_list_logs_filter_since(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """since parameter limits results to logs at or after the given datetime."""
        log = _make_mock_log(level="INFO", source="ingestion")

        mock_db.execute.side_effect = [
            _scalar_one_result(1),
            _scalars_all_result([log]),
        ]

        resp = await admin_client.get(
            f"{BASE}/",
            params={"since": "2024-01-01T00:00:00Z"},
        )

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_list_logs_filter_email_id(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """email_id parameter restricts logs to those referencing that email."""
        target_email_id = uuid.uuid4()
        log = _make_mock_log(level="INFO", source="crm_sync", email_id=target_email_id)

        mock_db.execute.side_effect = [
            _scalar_one_result(1),
            _scalars_all_result([log]),
        ]

        resp = await admin_client.get(f"{BASE}/", params={"email_id": str(target_email_id)})

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["email_id"] == str(target_email_id)

    async def test_list_logs_combined_filters(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Multiple filters are AND-combined; all matching logs are returned."""
        target_email_id = uuid.uuid4()
        log = _make_mock_log(
            level="ERROR",
            source="classification",
            email_id=target_email_id,
        )

        mock_db.execute.side_effect = [
            _scalar_one_result(1),
            _scalars_all_result([log]),
        ]

        resp = await admin_client.get(
            f"{BASE}/",
            params={
                "level": "ERROR",
                "source": "classification",
                "email_id": str(target_email_id),
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["level"] == "ERROR"
        assert item["source"] == "classification"
        assert item["email_id"] == str(target_email_id)


# ---------------------------------------------------------------------------
# TestListLogsPagination
# ---------------------------------------------------------------------------


class TestListLogsPagination:
    """GET /api/v1/logs/ — pagination behavior."""

    async def test_list_logs_default_pagination(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Default response carries limit=50 and offset=0."""
        mock_db.execute.side_effect = [
            _scalar_one_result(0),
            _scalars_all_result([]),
        ]

        resp = await admin_client.get(f"{BASE}/")

        assert resp.status_code == 200
        body = resp.json()
        assert body["limit"] == 50
        assert body["offset"] == 0

    async def test_list_logs_custom_pagination(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Custom limit and offset are reflected in the response envelope."""
        logs: list[object] = [_make_mock_log() for _ in range(10)]

        mock_db.execute.side_effect = [
            _scalar_one_result(100),
            _scalars_all_result(logs),
        ]

        resp = await admin_client.get(f"{BASE}/", params={"limit": 10, "offset": 5})

        assert resp.status_code == 200
        body = resp.json()
        assert body["limit"] == 10
        assert body["offset"] == 5
        assert body["total"] == 100
        assert len(body["items"]) == 10

    async def test_list_logs_limit_max(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """limit=200 (upper boundary) is valid and returns 200."""
        mock_db.execute.side_effect = [
            _scalar_one_result(0),
            _scalars_all_result([]),
        ]

        resp = await admin_client.get(f"{BASE}/", params={"limit": 200})

        assert resp.status_code == 200
        assert resp.json()["limit"] == 200

    async def test_list_logs_limit_exceeded(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """limit=201 exceeds the maximum — FastAPI returns 422 Unprocessable Entity."""
        resp = await admin_client.get(f"{BASE}/", params={"limit": 201})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TestListLogsSchema
# ---------------------------------------------------------------------------


class TestListLogsSchema:
    """GET /api/v1/logs/ — response schema correctness."""

    async def test_log_context_is_dict_str_str(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """context field is a dict[str, str] — string keys and string values only."""
        log = _make_mock_log()
        log.context = {"pipeline_stage": "classification", "email_id": str(uuid.uuid4())}

        mock_db.execute.side_effect = [
            _scalar_one_result(1),
            _scalars_all_result([log]),
        ]

        resp = await admin_client.get(f"{BASE}/")

        assert resp.status_code == 200
        context = resp.json()["items"][0]["context"]
        assert isinstance(context, dict)
        for key, value in context.items():
            assert isinstance(key, str)
            assert isinstance(value, str)

    async def test_log_item_fields_are_present(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Each log item exposes all required LogEntry fields."""
        log_id = uuid.uuid4()
        log = _make_mock_log(log_id=log_id, level="WARNING", source="draft_generation")

        mock_db.execute.side_effect = [
            _scalar_one_result(1),
            _scalars_all_result([log]),
        ]

        resp = await admin_client.get(f"{BASE}/")

        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["id"] == str(log_id)
        assert item["level"] == "WARNING"
        assert item["source"] == "draft_generation"
        assert item["message"] == "Test log message"
        assert "timestamp" in item
        assert "context" in item

    async def test_log_email_id_none_when_not_set(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """email_id is null in the response when the log has no associated email."""
        log = _make_mock_log(email_id=None)
        log.email_id = None

        mock_db.execute.side_effect = [
            _scalar_one_result(1),
            _scalars_all_result([log]),
        ]

        resp = await admin_client.get(f"{BASE}/")

        assert resp.status_code == 200
        assert resp.json()["items"][0]["email_id"] is None


# ---------------------------------------------------------------------------
# TestListLogsAuth
# ---------------------------------------------------------------------------


class TestListLogsAuth:
    """GET /api/v1/logs/ — authentication enforcement."""

    async def test_unauthenticated_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """Requests without a token receive 401 Unauthorized."""
        resp = await unauthenticated_client.get(f"{BASE}/")
        assert resp.status_code == 401
