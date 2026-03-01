"""Tests for the Redis lock mechanism in poll_email_accounts_job.

The scheduler uses a producer-side lock (Redis SET NX EX) to prevent enqueueing
``ingest_task`` multiple times for the same account before the previous run
completes.  These tests verify the lock lifecycle in isolation from the actual
Redis service by patching ``Redis.from_url`` at the import site
(``src.scheduler.jobs.Redis``).

Scenarios:
  1. Lock acquired (SET NX returns truthy)       -> ingest_task enqueued.
  2. Lock already held (SET NX returns None)     -> task NOT enqueued, silent skip.
  3. Enqueue failure after lock acquired         -> lock released (DELETE called).
  4. Lock TTL passed correctly                   -> ex=settings.pipeline_scheduler_lock_ttl_seconds.
  5. Lock key encodes account_id                 -> key is "{prefix}:{account_id}".
  6. Redis error on SET NX                       -> account skipped, no crash.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

ACCOUNT_ID = "account-abc-123"
LOCK_PREFIX = "mailwise:scheduler:lock"
LOCK_TTL = 300
REDIS_URL = "redis://localhost:6379/0"


def _make_mock_settings() -> MagicMock:
    """Return a Settings mock with known scheduler values."""
    settings = MagicMock()
    settings.redis_url = REDIS_URL
    settings.pipeline_scheduler_lock_key_prefix = LOCK_PREFIX
    settings.pipeline_scheduler_lock_ttl_seconds = LOCK_TTL
    settings.polling_interval_seconds = LOCK_TTL
    return settings


def _make_mock_redis(*, set_return: object = True) -> AsyncMock:
    """Return an AsyncMock Redis client.

    ``set_return`` controls what ``redis.set()`` returns:
    - truthy (default ``True``) -> lock acquired
    - ``None`` or ``False``     -> lock not acquired
    """
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=set_return)
    redis.delete = AsyncMock(return_value=1)
    redis.aclose = AsyncMock()
    return redis


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestSchedulerLock:
    """Lock lifecycle tests for poll_email_accounts_job."""

    @pytest.mark.asyncio
    async def test_lock_acquisition_success(self) -> None:
        """SET NX returns truthy -> lock acquired and ingest_task enqueued."""
        mock_redis = _make_mock_redis(set_return=True)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis") as mock_redis_cls,
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=[ACCOUNT_ID]),
            patch("src.scheduler.jobs._enqueue_ingest_task") as mock_enqueue,
        ):
            mock_redis_cls.from_url.return_value = mock_redis

            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        mock_enqueue.assert_called_once_with(ACCOUNT_ID, mock_settings)

    @pytest.mark.asyncio
    async def test_lock_acquisition_fails_when_held(self) -> None:
        """SET NX returns None (lock held by another worker) -> task NOT enqueued."""
        mock_redis = _make_mock_redis(set_return=None)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis") as mock_redis_cls,
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=[ACCOUNT_ID]),
            patch("src.scheduler.jobs._enqueue_ingest_task") as mock_enqueue,
        ):
            mock_redis_cls.from_url.return_value = mock_redis

            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        mock_enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_lock_released_on_enqueue_failure(self) -> None:
        """Lock acquired but _enqueue_ingest_task raises -> redis.delete() called."""
        mock_redis = _make_mock_redis(set_return=True)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis") as mock_redis_cls,
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=[ACCOUNT_ID]),
            patch(
                "src.scheduler.jobs._enqueue_ingest_task",
                side_effect=RuntimeError("Celery broker unavailable"),
            ),
        ):
            mock_redis_cls.from_url.return_value = mock_redis

            from src.scheduler.jobs import poll_email_accounts_job

            # The function must NOT propagate the enqueue failure
            await poll_email_accounts_job()

        expected_key = f"{LOCK_PREFIX}:{ACCOUNT_ID}"
        mock_redis.delete.assert_awaited_once_with(expected_key)

    @pytest.mark.asyncio
    async def test_lock_ttl_set_correctly(self) -> None:
        """redis.set() receives ex=settings.pipeline_scheduler_lock_ttl_seconds."""
        mock_redis = _make_mock_redis(set_return=True)
        mock_settings = _make_mock_settings()
        mock_settings.pipeline_scheduler_lock_ttl_seconds = 600  # override to distinct value

        with (
            patch("src.scheduler.jobs.Redis") as mock_redis_cls,
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=[ACCOUNT_ID]),
            patch("src.scheduler.jobs._enqueue_ingest_task"),
        ):
            mock_redis_cls.from_url.return_value = mock_redis

            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        mock_redis.set.assert_awaited_once()
        _, call_kwargs = mock_redis.set.call_args
        assert call_kwargs["ex"] == 600

    @pytest.mark.asyncio
    async def test_lock_key_includes_account_id(self) -> None:
        """Lock key is ``{prefix}:{account_id}`` — account isolation guarantee."""
        mock_redis = _make_mock_redis(set_return=True)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis") as mock_redis_cls,
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=[ACCOUNT_ID]),
            patch("src.scheduler.jobs._enqueue_ingest_task"),
        ):
            mock_redis_cls.from_url.return_value = mock_redis

            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        expected_key = f"{LOCK_PREFIX}:{ACCOUNT_ID}"
        call_args, _ = mock_redis.set.call_args
        assert call_args[0] == expected_key

    @pytest.mark.asyncio
    async def test_redis_error_on_lock_skips_account(self) -> None:
        """redis.set() raises RedisError -> account skipped, function does not crash."""
        mock_redis = _make_mock_redis()
        mock_redis.set = AsyncMock(side_effect=ConnectionError("Redis unreachable"))
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis") as mock_redis_cls,
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=[ACCOUNT_ID]),
            patch("src.scheduler.jobs._enqueue_ingest_task") as mock_enqueue,
        ):
            mock_redis_cls.from_url.return_value = mock_redis

            from src.scheduler.jobs import poll_email_accounts_job

            # Must complete without raising
            await poll_email_accounts_job()

        # Account skipped — enqueue never called
        mock_enqueue.assert_not_called()

    # -----------------------------------------------------------------------
    # Additional coverage: multi-account and connection lifecycle
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_redis_aclose_called_in_finally(self) -> None:
        """redis.aclose() is always called regardless of per-account outcome."""
        mock_redis = _make_mock_redis(set_return=True)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis") as mock_redis_cls,
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=[]),
            patch("src.scheduler.jobs._enqueue_ingest_task"),
        ):
            mock_redis_cls.from_url.return_value = mock_redis

            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        mock_redis.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aclose_called_even_when_enqueue_fails(self) -> None:
        """redis.aclose() is called in finally even if _enqueue_ingest_task raises."""
        mock_redis = _make_mock_redis(set_return=True)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis") as mock_redis_cls,
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=[ACCOUNT_ID]),
            patch(
                "src.scheduler.jobs._enqueue_ingest_task",
                side_effect=RuntimeError("broker down"),
            ),
        ):
            mock_redis_cls.from_url.return_value = mock_redis

            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        mock_redis.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiple_accounts_each_get_distinct_lock_key(self) -> None:
        """Each account_id results in an independent SET NX call with its own key."""
        account_a = "account-aaa"
        account_b = "account-bbb"
        mock_redis = _make_mock_redis(set_return=True)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis") as mock_redis_cls,
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch(
                "src.scheduler.jobs._get_active_accounts",
                return_value=[account_a, account_b],
            ),
            patch("src.scheduler.jobs._enqueue_ingest_task"),
        ):
            mock_redis_cls.from_url.return_value = mock_redis

            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        assert mock_redis.set.await_count == 2
        called_keys = [call.args[0] for call in mock_redis.set.call_args_list]
        assert f"{LOCK_PREFIX}:{account_a}" in called_keys
        assert f"{LOCK_PREFIX}:{account_b}" in called_keys

    @pytest.mark.asyncio
    async def test_lock_not_released_on_successful_enqueue(self) -> None:
        """Successful enqueue must NOT call redis.delete — lock expires by TTL."""
        mock_redis = _make_mock_redis(set_return=True)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis") as mock_redis_cls,
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=[ACCOUNT_ID]),
            patch("src.scheduler.jobs._enqueue_ingest_task"),
        ):
            mock_redis_cls.from_url.return_value = mock_redis

            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        mock_redis.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_set_nx_flag_passed(self) -> None:
        """redis.set() is called with nx=True to implement mutual exclusion."""
        mock_redis = _make_mock_redis(set_return=True)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis") as mock_redis_cls,
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=[ACCOUNT_ID]),
            patch("src.scheduler.jobs._enqueue_ingest_task"),
        ):
            mock_redis_cls.from_url.return_value = mock_redis

            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        _, call_kwargs = mock_redis.set.call_args
        assert call_kwargs["nx"] is True

    @pytest.mark.asyncio
    async def test_no_accounts_returns_without_error(self) -> None:
        """Empty account list -> no SET NX calls, no crash."""
        mock_redis = _make_mock_redis()
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis") as mock_redis_cls,
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=[]),
            patch("src.scheduler.jobs._enqueue_ingest_task") as mock_enqueue,
        ):
            mock_redis_cls.from_url.return_value = mock_redis

            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        mock_redis.set.assert_not_awaited()
        mock_enqueue.assert_not_called()
