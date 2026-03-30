"""Async Redis client for refresh token storage.

Invariants: Redis URL from Settings. Tokens are opaque UUID strings.
Guarantees: set/get/delete operate on key "refresh:{token}".
Errors raised: RedisClientError (wraps ConnectionError + TimeoutError).
Errors silenced: None — all errors re-raised as typed exceptions.
External state: Redis server (requires docker-compose redis service).
"""

from datetime import timedelta

import redis.asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from src.core.config import get_settings

_REFRESH_KEY_PREFIX = "refresh:"


class RedisClientError(Exception):
    """Raised when a Redis operation fails due to connection or timeout."""


_redis_client: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    """Get or create the async Redis client singleton.

    Lazy initialization avoids reading Settings at import time
    (same pattern as database.py engines).
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(  # type: ignore[no-untyped-call]
            settings.redis_url,
            decode_responses=True,
        )
    return _redis_client


async def set_refresh_token(
    token: str,
    user_id: str,
    ttl_days: int | None = None,
) -> None:
    """Store a refresh token in Redis with TTL.

    Invariants:
      - token: opaque UUID string (from create_refresh_token()).
      - user_id: string UUID of the authenticated user.
      - ttl_days: override for Settings.jwt_refresh_ttl_days (used in tests).

    Guarantees:
      - Key "refresh:{token}" set with value user_id.
      - TTL set to ttl_days (or settings default).

    Errors: RedisClientError on ConnectionError or TimeoutError.
    """
    settings = get_settings()
    days = ttl_days if ttl_days is not None else settings.jwt_refresh_ttl_days
    key = f"{_REFRESH_KEY_PREFIX}{token}"
    try:
        client = await _get_redis()
        await client.setex(key, timedelta(days=days), user_id)
    except RedisConnectionError as exc:
        raise RedisClientError(f"Redis connection failed: {exc}") from exc
    except RedisTimeoutError as exc:
        raise RedisClientError(f"Redis operation timed out: {exc}") from exc


async def get_refresh_token(token: str) -> str | None:
    """Retrieve the user_id associated with a refresh token.

    Invariants:
      - token: opaque UUID string.

    Guarantees:
      - Returns user_id (str) if token exists and has not expired.
      - Returns None if token does not exist or has expired.

    Errors: RedisClientError on ConnectionError or TimeoutError.
    """
    key = f"{_REFRESH_KEY_PREFIX}{token}"
    try:
        client = await _get_redis()
        result = await client.get(key)
    except RedisConnectionError as exc:
        raise RedisClientError(f"Redis connection failed: {exc}") from exc
    except RedisTimeoutError as exc:
        raise RedisClientError(f"Redis operation timed out: {exc}") from exc
    return result  # type: ignore[no-any-return]


async def delete_refresh_token(token: str) -> None:
    """Delete a refresh token from Redis (logout / revocation).

    Invariants:
      - token: opaque UUID string.

    Guarantees:
      - Key "refresh:{token}" is deleted.
      - No error if key does not exist (idempotent).

    Errors: RedisClientError on ConnectionError or TimeoutError.
    """
    key = f"{_REFRESH_KEY_PREFIX}{token}"
    try:
        client = await _get_redis()
        await client.delete(key)
    except RedisConnectionError as exc:
        raise RedisClientError(f"Redis connection failed: {exc}") from exc
    except RedisTimeoutError as exc:
        raise RedisClientError(f"Redis operation timed out: {exc}") from exc


async def close_redis() -> None:
    """Close the Redis connection pool. Call on app shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
