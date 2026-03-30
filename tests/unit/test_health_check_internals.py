"""Tests for health router private functions _check_db and _check_redis.

The health router mounts at /api/v1/health.  The existing
tests/api/test_health_router.py cover the endpoint itself by patching
_check_db and _check_redis.  These unit tests cover the actual
implementations of those private functions in isolation.

Coverage targets:
  1. _check_db: successful SELECT 1 returns ok AdapterHealthItem
  2. _check_db: asyncio.TimeoutError returns degraded with 'timeout' error
  3. _check_db: generic Exception returns unavailable with error message
  4. _check_redis: successful ping returns ok AdapterHealthItem
  5. _check_redis: asyncio.TimeoutError returns degraded with 'timeout' error
  6. _check_redis: generic Exception returns unavailable with error message

Mocking strategy:
  - async_engine: patched in src.api.routers.health via sys.modules injection.
  - _get_redis: patched in src.adapters.redis_client to return mock client.
  - asyncio.wait_for: patched to simulate timeout or success.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Tests for _check_db
# ---------------------------------------------------------------------------


class TestCheckDb:
    """_check_db — PostgreSQL health check."""

    async def test_successful_query_returns_ok_item(self) -> None:
        """SELECT 1 succeeds → AdapterHealthItem(status='ok', name='database')."""
        from src.api.routers.health import _check_db

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        mock_engine = MagicMock()
        mock_engine.connect = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        with (
            patch("src.api.routers.health.asyncio.wait_for", new_callable=AsyncMock) as mock_wait,
            patch("src.core.database.async_engine", mock_engine),
        ):
            mock_wait.return_value = None  # SELECT 1 succeeded

            import sys

            with patch.dict(
                sys.modules,
                {
                    "src.core.database": MagicMock(async_engine=mock_engine),
                },
            ):
                result = await _check_db(0.2)

        assert result.name == "database"
        assert result.status == "ok"
        assert result.latency_ms is not None

    async def test_timeout_returns_degraded_item(self) -> None:
        """asyncio.TimeoutError during SELECT 1 → degraded with error='timeout'."""
        from src.api.routers.health import _check_db

        mock_conn = AsyncMock()
        mock_engine = MagicMock()
        mock_engine.connect = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        with (
            patch("src.api.routers.health.asyncio.wait_for", side_effect=TimeoutError),
            patch("src.core.database.async_engine", mock_engine),
        ):
            import sys

            with patch.dict(
                sys.modules,
                {"src.core.database": MagicMock(async_engine=mock_engine)},
            ):
                result = await _check_db(0.2)

        assert result.name == "database"
        assert result.status == "degraded"
        assert result.error == "timeout"

    async def test_connection_error_returns_unavailable_item(self) -> None:
        """Connection error → unavailable with error message."""
        from src.api.routers.health import _check_db

        mock_engine = MagicMock()
        mock_engine.connect = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(side_effect=OSError("connection refused")),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        import sys

        with patch.dict(
            sys.modules,
            {"src.core.database": MagicMock(async_engine=mock_engine)},
        ):
            result = await _check_db(0.2)

        assert result.name == "database"
        assert result.status == "unavailable"
        assert result.error is not None


# ---------------------------------------------------------------------------
# Tests for _check_redis
# ---------------------------------------------------------------------------


class TestCheckRedis:
    """_check_redis — Redis health check."""

    async def test_successful_ping_returns_ok_item(self) -> None:
        """Successful ping → AdapterHealthItem(status='ok', name='redis')."""
        from src.api.routers.health import _check_redis

        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)

        with patch(
            "src.api.routers.health.asyncio.wait_for",
            new_callable=AsyncMock,
        ) as mock_wait:
            # First call returns mock client, second call returns True (ping)
            mock_wait.side_effect = [mock_client, True]

            result = await _check_redis(0.2)

        assert result.name == "redis"
        assert result.status == "ok"
        assert result.latency_ms is not None

    async def test_timeout_returns_degraded_item(self) -> None:
        """TimeoutError during ping → degraded with error='timeout'."""
        from src.api.routers.health import _check_redis

        with patch(
            "src.api.routers.health.asyncio.wait_for",
            side_effect=TimeoutError,
        ):
            result = await _check_redis(0.2)

        assert result.name == "redis"
        assert result.status == "degraded"
        assert result.error == "timeout"

    async def test_exception_returns_unavailable_item(self) -> None:
        """Generic Exception during ping → unavailable with error message."""
        from src.api.routers.health import _check_redis

        with patch(
            "src.api.routers.health.asyncio.wait_for",
            side_effect=ConnectionError("redis refused"),
        ):
            result = await _check_redis(0.2)

        assert result.name == "redis"
        assert result.status == "unavailable"
        assert result.error is not None
