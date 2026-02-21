"""Integration tests for src.adapters.redis_client.

Tests operate against a real Redis instance (REDIS_URL from Settings).
All external-state operations use structured try/except in production code
(D7). Tests verify the error-surface by monkeypatching _get_redis to inject
controlled failures — mocking only the external-state layer, not local logic.

Run with: pytest tests/integration/test_redis_client.py --run-integration
"""

import uuid
from collections.abc import Generator
from unittest import mock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from src.adapters.redis_client import (
    _REFRESH_KEY_PREFIX,
    RedisClientError,
    _get_redis,
    delete_refresh_token,
    get_refresh_token,
    set_refresh_token,
)

# ---------------------------------------------------------------------------
# Per-test Redis singleton reset — avoids event loop mismatch.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_redis_singleton() -> Generator[None, None, None]:
    """Reset the Redis singleton before each test.

    Each @pytest.mark.asyncio test gets a function-scoped event loop.
    The redis singleton retains a connection from the previous loop,
    causing 'Event loop is closed' errors. Resetting the global to None
    forces a fresh connection on the current test's loop.
    """
    import src.adapters.redis_client as _redis_mod

    _redis_mod._redis_client = None
    yield
    _redis_mod._redis_client = None


# ---------------------------------------------------------------------------
# TestRefreshTokenLifecycle
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRefreshTokenLifecycle:
    """Full lifecycle of refresh tokens in Redis: set, get, delete, TTL."""

    @pytest.mark.asyncio
    async def test_set_and_get(self) -> None:
        """set_refresh_token stores a token; get_refresh_token retrieves the user_id."""
        token = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        await set_refresh_token(token, user_id, ttl_days=1)
        result = await get_refresh_token(token)

        assert result == user_id

        # Cleanup.
        await delete_refresh_token(token)

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self) -> None:
        """get_refresh_token returns None for a token that was never stored."""
        random_token = str(uuid.uuid4())
        result = await get_refresh_token(random_token)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_token(self) -> None:
        """After delete_refresh_token, get_refresh_token returns None."""
        token = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        await set_refresh_token(token, user_id, ttl_days=1)
        await delete_refresh_token(token)
        result = await get_refresh_token(token)

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_no_error(self) -> None:
        """delete_refresh_token on a nonexistent key raises no exception.

        Idempotency invariant: logout is safe to call multiple times.
        """
        random_token = str(uuid.uuid4())
        # Must not raise.
        await delete_refresh_token(random_token)

    @pytest.mark.asyncio
    async def test_ttl_is_set(self) -> None:
        """TTL is positive for a freshly stored refresh token.

        Verifies the Redis SETEX call actually applied the expiry.
        Uses _get_redis() directly — the lowest-level public interface —
        to inspect the TTL without going through the business-logic helpers.
        """
        token = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        await set_refresh_token(token, user_id, ttl_days=1)
        key = f"{_REFRESH_KEY_PREFIX}{token}"

        try:
            client = await _get_redis()
            ttl: int = await client.ttl(key)
        finally:
            await delete_refresh_token(token)

        # TTL must be positive — a value of -1 means no expiry was set,
        # -2 means the key does not exist.
        assert ttl > 0


# ---------------------------------------------------------------------------
# TestRedisErrorHandling
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRedisErrorHandling:
    """Error translation: Redis exceptions are wrapped in RedisClientError.

    try-except D7: set_refresh_token / get_refresh_token / delete_refresh_token
    must catch ConnectionError and TimeoutError and raise RedisClientError.
    Tests monkeypatch _get_redis to inject controlled failures, verifying only
    the external-state boundary — no local-computation logic is exercised.
    """

    @pytest.mark.asyncio
    async def test_connection_error_raises_redis_client_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ConnectionError from Redis is wrapped in RedisClientError.

        Monkeypatches _get_redis to return a mock client whose setex()
        raises RedisConnectionError — simulating a broken Redis connection
        at the external-state boundary.
        """

        async def _mock_get_redis_conn_error() -> mock.AsyncMock:
            client = mock.AsyncMock()
            client.setex.side_effect = RedisConnectionError("connection refused")
            return client

        monkeypatch.setattr(
            "src.adapters.redis_client._get_redis",
            _mock_get_redis_conn_error,
        )

        with pytest.raises(RedisClientError, match="Redis connection failed"):
            await set_refresh_token(str(uuid.uuid4()), str(uuid.uuid4()), ttl_days=1)

    @pytest.mark.asyncio
    async def test_timeout_error_raises_redis_client_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """TimeoutError from Redis is wrapped in RedisClientError.

        Monkeypatches _get_redis to return a mock client whose get()
        raises RedisTimeoutError — simulating a slow/overloaded Redis.
        """

        async def _mock_get_redis_timeout() -> mock.AsyncMock:
            client = mock.AsyncMock()
            client.get.side_effect = RedisTimeoutError("operation timed out")
            return client

        monkeypatch.setattr(
            "src.adapters.redis_client._get_redis",
            _mock_get_redis_timeout,
        )

        with pytest.raises(RedisClientError, match="Redis operation timed out"):
            await get_refresh_token(str(uuid.uuid4()))
