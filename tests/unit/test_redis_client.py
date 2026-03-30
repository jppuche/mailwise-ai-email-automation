"""Tests for src/adapters/redis_client.py — mocked aioredis.Redis.

Coverage targets:
  1. set_refresh_token: happy path stores key with TTL
  2. set_refresh_token: ConnectionError raises RedisClientError
  3. set_refresh_token: TimeoutError raises RedisClientError
  4. set_refresh_token: custom ttl_days overrides settings default
  5. get_refresh_token: found token returns user_id string
  6. get_refresh_token: missing token returns None
  7. get_refresh_token: ConnectionError raises RedisClientError
  8. get_refresh_token: TimeoutError raises RedisClientError
  9. delete_refresh_token: happy path calls redis.delete
 10. delete_refresh_token: ConnectionError raises RedisClientError
 11. close_redis: aclose called and singleton reset to None
 12. close_redis: no-op when client is None

Structured exceptions — ConnectionError and TimeoutError handled separately,
not as bare except Exception.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from src.adapters.redis_client import (
    RedisClientError,
    close_redis,
    delete_refresh_token,
    get_refresh_token,
    set_refresh_token,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_redis(
    *,
    setex_side_effect: BaseException | None = None,
    get_return_value: object = "user-id-123",
    get_side_effect: BaseException | None = None,
    delete_side_effect: BaseException | None = None,
) -> AsyncMock:
    redis = AsyncMock()
    if setex_side_effect:
        redis.setex = AsyncMock(side_effect=setex_side_effect)
    else:
        redis.setex = AsyncMock(return_value=True)

    if get_side_effect:
        redis.get = AsyncMock(side_effect=get_side_effect)
    else:
        redis.get = AsyncMock(return_value=get_return_value)

    if delete_side_effect:
        redis.delete = AsyncMock(side_effect=delete_side_effect)
    else:
        redis.delete = AsyncMock(return_value=1)

    redis.aclose = AsyncMock()
    return redis


def _make_settings(*, jwt_refresh_ttl_days: int = 7) -> MagicMock:
    settings = MagicMock()
    settings.redis_url = "redis://localhost:6379/0"
    settings.jwt_refresh_ttl_days = jwt_refresh_ttl_days
    return settings


# ---------------------------------------------------------------------------
# TestSetRefreshToken
# ---------------------------------------------------------------------------


class TestSetRefreshToken:
    async def test_happy_path_calls_setex_with_correct_key(self) -> None:
        """set_refresh_token stores key 'refresh:{token}' with user_id value."""
        mock_redis = _make_mock_redis()
        settings = _make_settings(jwt_refresh_ttl_days=7)

        with (
            patch("src.adapters.redis_client._get_redis", return_value=mock_redis),
            patch("src.adapters.redis_client.get_settings", return_value=settings),
        ):
            await set_refresh_token("token-abc", "user-123")

        mock_redis.setex.assert_awaited_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[0] == "refresh:token-abc"
        assert call_args[2] == "user-123"

    async def test_custom_ttl_days_overrides_settings(self) -> None:
        """When ttl_days is specified, it overrides the settings default."""
        from datetime import timedelta

        mock_redis = _make_mock_redis()
        settings = _make_settings(jwt_refresh_ttl_days=7)

        with (
            patch("src.adapters.redis_client._get_redis", return_value=mock_redis),
            patch("src.adapters.redis_client.get_settings", return_value=settings),
        ):
            await set_refresh_token("token-xyz", "user-456", ttl_days=30)

        call_args = mock_redis.setex.call_args[0]
        assert call_args[1] == timedelta(days=30)

    async def test_connection_error_raises_redis_client_error(self) -> None:
        """RedisConnectionError wraps to RedisClientError."""
        mock_redis = _make_mock_redis(setex_side_effect=RedisConnectionError("refused"))
        settings = _make_settings()

        with (
            patch("src.adapters.redis_client._get_redis", return_value=mock_redis),
            patch("src.adapters.redis_client.get_settings", return_value=settings),
            pytest.raises(RedisClientError, match="connection failed"),
        ):
            await set_refresh_token("token", "user")

    async def test_timeout_error_raises_redis_client_error(self) -> None:
        """RedisTimeoutError wraps to RedisClientError."""
        mock_redis = _make_mock_redis(setex_side_effect=RedisTimeoutError("timed out"))
        settings = _make_settings()

        with (
            patch("src.adapters.redis_client._get_redis", return_value=mock_redis),
            patch("src.adapters.redis_client.get_settings", return_value=settings),
            pytest.raises(RedisClientError, match="timed out"),
        ):
            await set_refresh_token("token", "user")


# ---------------------------------------------------------------------------
# TestGetRefreshToken
# ---------------------------------------------------------------------------


class TestGetRefreshToken:
    async def test_existing_token_returns_user_id(self) -> None:
        """Found token returns the stored user_id string."""
        mock_redis = _make_mock_redis(get_return_value="user-999")

        with patch("src.adapters.redis_client._get_redis", return_value=mock_redis):
            result = await get_refresh_token("token-abc")

        assert result == "user-999"

    async def test_missing_token_returns_none(self) -> None:
        """Token not found (redis.get returns None) → function returns None."""
        mock_redis = _make_mock_redis(get_return_value=None)

        with patch("src.adapters.redis_client._get_redis", return_value=mock_redis):
            result = await get_refresh_token("nonexistent-token")

        assert result is None

    async def test_connection_error_raises_redis_client_error(self) -> None:
        """RedisConnectionError wraps to RedisClientError."""
        mock_redis = _make_mock_redis(get_side_effect=RedisConnectionError("refused"))

        with (
            patch("src.adapters.redis_client._get_redis", return_value=mock_redis),
            pytest.raises(RedisClientError, match="connection failed"),
        ):
            await get_refresh_token("token")

    async def test_timeout_error_raises_redis_client_error(self) -> None:
        """RedisTimeoutError wraps to RedisClientError."""
        mock_redis = _make_mock_redis(get_side_effect=RedisTimeoutError("timeout"))

        with (
            patch("src.adapters.redis_client._get_redis", return_value=mock_redis),
            pytest.raises(RedisClientError, match="timed out"),
        ):
            await get_refresh_token("token")

    async def test_correct_key_format_used(self) -> None:
        """Key 'refresh:{token}' is passed to redis.get."""
        mock_redis = _make_mock_redis(get_return_value="uid")

        with patch("src.adapters.redis_client._get_redis", return_value=mock_redis):
            await get_refresh_token("my-token")

        mock_redis.get.assert_awaited_once_with("refresh:my-token")


# ---------------------------------------------------------------------------
# TestDeleteRefreshToken
# ---------------------------------------------------------------------------


class TestDeleteRefreshToken:
    async def test_happy_path_calls_redis_delete(self) -> None:
        """delete_refresh_token calls redis.delete with correct key."""
        mock_redis = _make_mock_redis()

        with patch("src.adapters.redis_client._get_redis", return_value=mock_redis):
            await delete_refresh_token("token-del")

        mock_redis.delete.assert_awaited_once_with("refresh:token-del")

    async def test_connection_error_raises_redis_client_error(self) -> None:
        """RedisConnectionError wraps to RedisClientError."""
        mock_redis = _make_mock_redis(delete_side_effect=RedisConnectionError("down"))

        with (
            patch("src.adapters.redis_client._get_redis", return_value=mock_redis),
            pytest.raises(RedisClientError, match="connection failed"),
        ):
            await delete_refresh_token("token")

    async def test_timeout_error_raises_redis_client_error(self) -> None:
        """RedisTimeoutError wraps to RedisClientError."""
        mock_redis = _make_mock_redis(delete_side_effect=RedisTimeoutError("timeout"))

        with (
            patch("src.adapters.redis_client._get_redis", return_value=mock_redis),
            pytest.raises(RedisClientError, match="timed out"),
        ):
            await delete_refresh_token("token")


# ---------------------------------------------------------------------------
# TestCloseRedis
# ---------------------------------------------------------------------------


class TestCloseRedis:
    async def test_aclose_called_and_singleton_reset(self) -> None:
        """close_redis calls aclose() and sets the singleton back to None."""
        import src.adapters.redis_client as rc

        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()

        # Inject the singleton directly
        original = rc._redis_client
        rc._redis_client = mock_redis
        try:
            await close_redis()

            mock_redis.aclose.assert_awaited_once()
            assert rc._redis_client is None
        finally:
            rc._redis_client = original

    async def test_no_op_when_client_is_none(self) -> None:
        """close_redis does nothing and does not raise when client is None."""
        import src.adapters.redis_client as rc

        original = rc._redis_client
        rc._redis_client = None
        try:
            await close_redis()  # must not raise
        finally:
            rc._redis_client = original


# ---------------------------------------------------------------------------
# TestGetRedis (singleton)
# ---------------------------------------------------------------------------


class TestGetRedisSingleton:
    async def test_singleton_created_on_first_call(self) -> None:
        """_get_redis creates a new Redis client when none exists."""
        import src.adapters.redis_client as rc

        settings = _make_settings()
        original = rc._redis_client
        rc._redis_client = None

        try:
            import redis.asyncio as aioredis

            mock_client = AsyncMock()
            with (
                patch.object(aioredis, "from_url", return_value=mock_client),
                patch("src.adapters.redis_client.get_settings", return_value=settings),
            ):
                client = await rc._get_redis()

            assert client is mock_client
            assert rc._redis_client is mock_client
        finally:
            rc._redis_client = original

    async def test_singleton_reused_on_subsequent_calls(self) -> None:
        """_get_redis returns the same instance on repeated calls."""
        import src.adapters.redis_client as rc

        original = rc._redis_client
        mock_client = AsyncMock()
        rc._redis_client = mock_client

        try:
            client = await rc._get_redis()
            assert client is mock_client
        finally:
            rc._redis_client = original
