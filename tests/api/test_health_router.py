"""Tests for GET /api/v1/health — aggregated health check.

Architecture notes:
  - Health endpoint is always HTTP 200 (never 503).
  - "degraded" when any adapter is not "ok".
  - _check_db and _check_redis are patched — no real DB/Redis connections.
  - No auth required (public endpoint).
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api.main import app
from src.api.schemas.common import AdapterHealthItem


@pytest_asyncio.fixture
async def health_client() -> AsyncGenerator[AsyncClient, None]:
    """Dedicated client for health tests — no auth or DB override needed."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


def _ok_db() -> AdapterHealthItem:
    return AdapterHealthItem(name="database", status="ok", latency_ms=5)


def _ok_redis() -> AdapterHealthItem:
    return AdapterHealthItem(name="redis", status="ok", latency_ms=2)


def _degraded_db() -> AdapterHealthItem:
    return AdapterHealthItem(name="database", status="degraded", error="timeout")


def _unavailable_redis() -> AdapterHealthItem:
    return AdapterHealthItem(name="redis", status="unavailable", error="connection refused")


class TestHealthEndpoint:
    """GET /api/v1/health — aggregated adapter health check."""

    async def test_no_auth_required(self, health_client: AsyncClient) -> None:
        """Health endpoint is public — requests without auth tokens succeed."""
        with (
            patch(
                "src.api.routers.health._check_db",
                new_callable=AsyncMock,
                return_value=_ok_db(),
            ),
            patch(
                "src.api.routers.health._check_redis",
                new_callable=AsyncMock,
                return_value=_ok_redis(),
            ),
        ):
            response = await health_client.get("/api/v1/health")

        assert response.status_code == 200

    async def test_all_ok_returns_ok_status(self, health_client: AsyncClient) -> None:
        """When all adapters report 'ok', overall status is 'ok'."""
        with (
            patch(
                "src.api.routers.health._check_db",
                new_callable=AsyncMock,
                return_value=_ok_db(),
            ),
            patch(
                "src.api.routers.health._check_redis",
                new_callable=AsyncMock,
                return_value=_ok_redis(),
            ),
        ):
            response = await health_client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    async def test_response_includes_two_adapters(self, health_client: AsyncClient) -> None:
        """Response lists exactly two adapters: database and redis."""
        with (
            patch(
                "src.api.routers.health._check_db",
                new_callable=AsyncMock,
                return_value=_ok_db(),
            ),
            patch(
                "src.api.routers.health._check_redis",
                new_callable=AsyncMock,
                return_value=_ok_redis(),
            ),
        ):
            response = await health_client.get("/api/v1/health")

        data = response.json()
        assert len(data["adapters"]) == 2
        adapter_names = {a["name"] for a in data["adapters"]}
        assert adapter_names == {"database", "redis"}

    async def test_response_includes_version(self, health_client: AsyncClient) -> None:
        """Response body includes a version string from settings."""
        with (
            patch(
                "src.api.routers.health._check_db",
                new_callable=AsyncMock,
                return_value=_ok_db(),
            ),
            patch(
                "src.api.routers.health._check_redis",
                new_callable=AsyncMock,
                return_value=_ok_redis(),
            ),
        ):
            response = await health_client.get("/api/v1/health")

        data = response.json()
        assert "version" in data
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0

    async def test_degraded_when_redis_unavailable(self, health_client: AsyncClient) -> None:
        """If redis is unavailable, overall status is 'degraded'. HTTP code is still 200."""
        with (
            patch(
                "src.api.routers.health._check_db",
                new_callable=AsyncMock,
                return_value=_ok_db(),
            ),
            patch(
                "src.api.routers.health._check_redis",
                new_callable=AsyncMock,
                return_value=_unavailable_redis(),
            ),
        ):
            response = await health_client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"

    async def test_degraded_when_db_times_out(self, health_client: AsyncClient) -> None:
        """If db reports 'degraded' (timeout), overall status is 'degraded'. HTTP 200."""
        with (
            patch(
                "src.api.routers.health._check_db",
                new_callable=AsyncMock,
                return_value=_degraded_db(),
            ),
            patch(
                "src.api.routers.health._check_redis",
                new_callable=AsyncMock,
                return_value=_ok_redis(),
            ),
        ):
            response = await health_client.get("/api/v1/health")

        assert response.status_code == 200
        assert response.json()["status"] == "degraded"

    async def test_degraded_when_all_unavailable(self, health_client: AsyncClient) -> None:
        """All adapters unavailable — HTTP 200, overall status 'degraded'."""
        with (
            patch(
                "src.api.routers.health._check_db",
                new_callable=AsyncMock,
                return_value=AdapterHealthItem(name="database", status="unavailable", error="down"),
            ),
            patch(
                "src.api.routers.health._check_redis",
                new_callable=AsyncMock,
                return_value=AdapterHealthItem(name="redis", status="unavailable", error="down"),
            ),
        ):
            response = await health_client.get("/api/v1/health")

        assert response.status_code == 200
        assert response.json()["status"] == "degraded"

    async def test_exception_from_gather_falls_back_to_unknown_adapter(
        self, health_client: AsyncClient
    ) -> None:
        """If asyncio.gather returns an exception (return_exceptions=True),
        the router wraps it as an 'unknown' AdapterHealthItem with status
        'unavailable'. Overall status becomes 'degraded'. HTTP 200.
        """

        # Simulate gather returning the exception as a value by patching gather itself
        async def _gather_with_exception(*coros, **kwargs):  # type: ignore[no-untyped-def]
            # Return one real AdapterHealthItem and one Exception object
            return [
                AdapterHealthItem(name="database", status="ok", latency_ms=1),
                RuntimeError("unexpected adapter crash"),
            ]

        with patch("src.api.routers.health.asyncio.gather", side_effect=_gather_with_exception):
            response = await health_client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        # The exception is wrapped as an 'unknown' adapter
        unknown = next((a for a in data["adapters"] if a["name"] == "unknown"), None)
        assert unknown is not None
        assert unknown["status"] == "unavailable"

    async def test_adapter_latency_ms_present_when_ok(self, health_client: AsyncClient) -> None:
        """Adapters with status 'ok' report a latency_ms value."""
        with (
            patch(
                "src.api.routers.health._check_db",
                new_callable=AsyncMock,
                return_value=_ok_db(),
            ),
            patch(
                "src.api.routers.health._check_redis",
                new_callable=AsyncMock,
                return_value=_ok_redis(),
            ),
        ):
            response = await health_client.get("/api/v1/health")

        data = response.json()
        for adapter in data["adapters"]:
            assert adapter["latency_ms"] is not None
            assert isinstance(adapter["latency_ms"], int)

    async def test_adapter_error_field_present_when_unavailable(
        self, health_client: AsyncClient
    ) -> None:
        """Adapters with status 'unavailable' report an error field."""
        with (
            patch(
                "src.api.routers.health._check_db",
                new_callable=AsyncMock,
                return_value=_ok_db(),
            ),
            patch(
                "src.api.routers.health._check_redis",
                new_callable=AsyncMock,
                return_value=_unavailable_redis(),
            ),
        ):
            response = await health_client.get("/api/v1/health")

        data = response.json()
        redis_item = next(a for a in data["adapters"] if a["name"] == "redis")
        assert redis_item["status"] == "unavailable"
        assert redis_item["error"] is not None
