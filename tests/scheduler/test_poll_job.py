"""Tests for poll_email_accounts_job and supporting functions in src/scheduler/jobs.py.

Scope:
  - poll_email_accounts_job: Redis lock per account, enqueue, cleanup.
  - _get_active_accounts: current stub returns [].
  - _enqueue_ingest_task: calls ingest_task.delay with correct args.

Mock strategy:
  - Redis is mocked via patch('src.scheduler.jobs.Redis') — the class imported
    at module level in jobs.py. from_url returns an AsyncMock instance so that
    redis.set / redis.delete / redis.aclose are all awaitable.
  - _get_active_accounts patched at 'src.scheduler.jobs._get_active_accounts'.
  - _enqueue_ingest_task patched at 'src.scheduler.jobs._enqueue_ingest_task'.
  - get_settings patched at 'src.scheduler.jobs.get_settings'.

All async tests run under pytest-asyncio auto mode (asyncio_mode = "auto" in
pyproject.toml) — no @pytest.mark.asyncio decorator needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.scheduler.jobs import _enqueue_ingest_task, _get_active_accounts

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_mock_settings(
    *,
    redis_url: str = "redis://localhost:6379/0",
    pipeline_scheduler_lock_key_prefix: str = "mailwise:scheduler:lock",
    pipeline_scheduler_lock_ttl_seconds: int = 300,
    polling_interval_seconds: int = 300,
) -> MagicMock:
    """Build a minimal mock Settings with fields accessed by jobs.py."""
    settings = MagicMock()
    settings.redis_url = redis_url
    settings.pipeline_scheduler_lock_key_prefix = pipeline_scheduler_lock_key_prefix
    settings.pipeline_scheduler_lock_ttl_seconds = pipeline_scheduler_lock_ttl_seconds
    settings.polling_interval_seconds = polling_interval_seconds
    return settings


def _make_mock_redis(*, lock_result: object = True) -> AsyncMock:
    """Build an AsyncMock Redis instance.

    lock_result controls what redis.set() returns:
      - True  -> lock acquired (NX set succeeded)
      - False -> lock not acquired (key already held)
      - Exception instance -> redis.set raises on call
    """
    redis = AsyncMock()
    if isinstance(lock_result, BaseException):
        redis.set.side_effect = lock_result
    else:
        redis.set.return_value = lock_result
    redis.delete = AsyncMock(return_value=1)
    redis.aclose = AsyncMock(return_value=None)
    return redis


def _redis_class_patch(mock_redis: AsyncMock) -> MagicMock:
    """Build a MagicMock Redis class whose from_url() returns mock_redis."""
    cls = MagicMock()
    cls.from_url.return_value = mock_redis
    return cls


# ---------------------------------------------------------------------------
# Tests: _get_active_accounts — direct unit test of the stub
# ---------------------------------------------------------------------------


class TestGetActiveAccounts:
    def test_returns_empty_list(self) -> None:
        """Current stub returns [] — no DB access yet."""
        result = _get_active_accounts()
        assert result == []

    def test_return_type_is_list(self) -> None:
        result = _get_active_accounts()
        assert isinstance(result, list)

    def test_all_elements_are_strings(self) -> None:
        """When the stub is replaced in future blocks, elements must be str."""
        result = _get_active_accounts()
        for item in result:
            assert isinstance(item, str)


# ---------------------------------------------------------------------------
# Tests: poll_email_accounts_job — no active accounts
# ---------------------------------------------------------------------------


class TestPollNoAccounts:
    async def test_no_accounts_skips_redis_set(self) -> None:
        """With no accounts, redis.set is never called."""
        mock_redis = _make_mock_redis()
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=[]),
            patch("src.scheduler.jobs._enqueue_ingest_task") as mock_enqueue,
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        mock_redis.set.assert_not_called()
        mock_enqueue.assert_not_called()

    async def test_no_accounts_still_closes_redis(self) -> None:
        """redis.aclose() must be called even with zero accounts (finally block)."""
        mock_redis = _make_mock_redis()
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=[]),
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        mock_redis.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: poll_email_accounts_job — successful enqueue
# ---------------------------------------------------------------------------


class TestPollEnqueuesForActiveAccounts:
    async def test_enqueues_for_each_account(self) -> None:
        """Lock acquired for both accounts -> enqueue called twice."""
        mock_redis = _make_mock_redis(lock_result=True)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc1", "acc2"]),
            patch("src.scheduler.jobs._enqueue_ingest_task") as mock_enqueue,
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        assert mock_enqueue.call_count == 2

    async def test_enqueue_called_with_correct_account_ids(self) -> None:
        """_enqueue_ingest_task receives the exact account_id and settings."""
        mock_redis = _make_mock_redis(lock_result=True)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc1", "acc2"]),
            patch("src.scheduler.jobs._enqueue_ingest_task") as mock_enqueue,
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        enqueued_accounts = [call.args[0] for call in mock_enqueue.call_args_list]
        assert sorted(enqueued_accounts) == ["acc1", "acc2"]

    async def test_enqueue_receives_settings_object(self) -> None:
        """_enqueue_ingest_task second arg is the settings object."""
        mock_redis = _make_mock_redis(lock_result=True)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc1"]),
            patch("src.scheduler.jobs._enqueue_ingest_task") as mock_enqueue,
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        _, settings_arg = mock_enqueue.call_args.args
        assert settings_arg is mock_settings

    async def test_lock_acquired_with_nx_and_ex(self) -> None:
        """redis.set called with nx=True and ex=lock_ttl_seconds."""
        mock_redis = _make_mock_redis(lock_result=True)
        mock_settings = _make_mock_settings(pipeline_scheduler_lock_ttl_seconds=120)

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc1"]),
            patch("src.scheduler.jobs._enqueue_ingest_task"),
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        call_kwargs = mock_redis.set.call_args.kwargs
        assert call_kwargs["nx"] is True
        assert call_kwargs["ex"] == 120

    async def test_lock_key_contains_account_id(self) -> None:
        """Lock key format: {prefix}:{account_id}."""
        mock_redis = _make_mock_redis(lock_result=True)
        mock_settings = _make_mock_settings(
            pipeline_scheduler_lock_key_prefix="mailwise:scheduler:lock"
        )

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc-xyz"]),
            patch("src.scheduler.jobs._enqueue_ingest_task"),
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        lock_key_arg = mock_redis.set.call_args.args[0]
        assert lock_key_arg == "mailwise:scheduler:lock:acc-xyz"

    async def test_redis_closed_after_successful_job(self) -> None:
        """redis.aclose() called exactly once after normal completion."""
        mock_redis = _make_mock_redis(lock_result=True)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc1"]),
            patch("src.scheduler.jobs._enqueue_ingest_task"),
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        mock_redis.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: poll_email_accounts_job — lock already held (skip)
# ---------------------------------------------------------------------------


class TestPollSkipsLockedAccounts:
    async def test_locked_account_not_enqueued(self) -> None:
        """redis.set returns False (None) -> account skipped, no enqueue."""
        mock_redis = _make_mock_redis(lock_result=None)  # None -> bool(None) == False
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc1"]),
            patch("src.scheduler.jobs._enqueue_ingest_task") as mock_enqueue,
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        mock_enqueue.assert_not_called()

    async def test_first_locked_second_enqueued(self) -> None:
        """acc1 lock held, acc2 lock free -> only acc2 enqueued."""
        mock_redis = AsyncMock()
        # First call (acc1): None -> not acquired; second call (acc2): True -> acquired
        mock_redis.set.side_effect = [None, True]
        mock_redis.delete = AsyncMock(return_value=1)
        mock_redis.aclose = AsyncMock(return_value=None)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc1", "acc2"]),
            patch("src.scheduler.jobs._enqueue_ingest_task") as mock_enqueue,
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        assert mock_enqueue.call_count == 1
        enqueued_account = mock_enqueue.call_args.args[0]
        assert enqueued_account == "acc2"

    async def test_all_locked_nothing_enqueued(self) -> None:
        """All accounts locked -> zero enqueues."""
        mock_redis = AsyncMock()
        mock_redis.set.return_value = None  # all locked
        mock_redis.delete = AsyncMock(return_value=1)
        mock_redis.aclose = AsyncMock(return_value=None)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch(
                "src.scheduler.jobs._get_active_accounts",
                return_value=["acc1", "acc2", "acc3"],
            ),
            patch("src.scheduler.jobs._enqueue_ingest_task") as mock_enqueue,
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        mock_enqueue.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: poll_email_accounts_job — Redis error on lock acquisition
# ---------------------------------------------------------------------------


class TestPollRedisErrorOnLockAcquisition:
    async def test_redis_error_on_lock_skips_account(self) -> None:
        """redis.set raises -> account skipped, no enqueue, loop continues."""
        redis_exc = ConnectionError("Redis unavailable")
        mock_redis = _make_mock_redis(lock_result=redis_exc)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc1"]),
            patch("src.scheduler.jobs._enqueue_ingest_task") as mock_enqueue,
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            # Must not raise — error is caught and logged
            await poll_email_accounts_job()

        mock_enqueue.assert_not_called()

    async def test_redis_error_on_first_account_does_not_block_second(self) -> None:
        """Lock error for acc1 -> acc2 still processed (per-account isolation)."""
        mock_redis = AsyncMock()
        mock_redis.set.side_effect = [ConnectionError("Redis down"), True]
        mock_redis.delete = AsyncMock(return_value=1)
        mock_redis.aclose = AsyncMock(return_value=None)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc1", "acc2"]),
            patch("src.scheduler.jobs._enqueue_ingest_task") as mock_enqueue,
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        assert mock_enqueue.call_count == 1
        assert mock_enqueue.call_args.args[0] == "acc2"

    async def test_redis_closed_after_lock_error(self) -> None:
        """redis.aclose() called even when lock acquisition raises."""
        redis_exc = ConnectionError("Redis unavailable")
        mock_redis = _make_mock_redis(lock_result=redis_exc)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc1"]),
            patch("src.scheduler.jobs._enqueue_ingest_task"),
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        mock_redis.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: poll_email_accounts_job — enqueue failure releases lock
# ---------------------------------------------------------------------------


class TestPollEnqueueFailureReleasesLock:
    async def test_enqueue_failure_calls_redis_delete(self) -> None:
        """_enqueue_ingest_task raises -> redis.delete(lock_key) called."""
        mock_redis = _make_mock_redis(lock_result=True)
        mock_settings = _make_mock_settings(
            pipeline_scheduler_lock_key_prefix="mailwise:scheduler:lock"
        )

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc1"]),
            patch(
                "src.scheduler.jobs._enqueue_ingest_task",
                side_effect=RuntimeError("Celery broker down"),
            ),
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        mock_redis.delete.assert_awaited_once_with("mailwise:scheduler:lock:acc1")

    async def test_enqueue_failure_does_not_propagate(self) -> None:
        """Enqueue error is caught -> job completes without raising."""
        mock_redis = _make_mock_redis(lock_result=True)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc1"]),
            patch(
                "src.scheduler.jobs._enqueue_ingest_task",
                side_effect=ValueError("bad argument"),
            ),
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            # Must not raise
            await poll_email_accounts_job()

    async def test_enqueue_failure_redis_closed_afterward(self) -> None:
        """redis.aclose() called even when enqueue fails."""
        mock_redis = _make_mock_redis(lock_result=True)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc1"]),
            patch(
                "src.scheduler.jobs._enqueue_ingest_task",
                side_effect=RuntimeError("broker gone"),
            ),
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        mock_redis.aclose.assert_awaited_once()

    async def test_enqueue_failure_second_account_still_processed(self) -> None:
        """Enqueue error for acc1 does not block acc2."""
        mock_redis = _make_mock_redis(lock_result=True)
        mock_settings = _make_mock_settings()
        call_count = 0

        def _enqueue_side_effect(account_id: str, settings: object) -> None:
            nonlocal call_count
            call_count += 1
            if account_id == "acc1":
                raise RuntimeError("broker down for acc1")

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc1", "acc2"]),
            patch(
                "src.scheduler.jobs._enqueue_ingest_task",
                side_effect=_enqueue_side_effect,
            ),
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        assert call_count == 2

    async def test_enqueue_failure_lock_delete_error_is_suppressed(self) -> None:
        """redis.delete raises during lock cleanup -> error suppressed, no propagation."""
        mock_redis = _make_mock_redis(lock_result=True)
        mock_redis.delete.side_effect = ConnectionError("Redis gone")
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc1"]),
            patch(
                "src.scheduler.jobs._enqueue_ingest_task",
                side_effect=RuntimeError("broker down"),
            ),
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            # Must not raise even if delete also fails
            await poll_email_accounts_job()

        mock_redis.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: poll_email_accounts_job — redis.aclose guaranteed (finally block)
# ---------------------------------------------------------------------------


class TestPollRedisAlwaysClosed:
    async def test_aclose_called_when_get_accounts_raises(self) -> None:
        """If _get_active_accounts raises, finally still closes Redis."""
        mock_redis = _make_mock_redis()
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch(
                "src.scheduler.jobs._get_active_accounts",
                side_effect=RuntimeError("DB gone"),
            ),
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            with pytest.raises(RuntimeError, match="DB gone"):
                await poll_email_accounts_job()

        mock_redis.aclose.assert_awaited_once()

    async def test_aclose_called_exactly_once_per_job_run(self) -> None:
        """aclose() is called exactly once per poll_email_accounts_job invocation."""
        mock_redis = _make_mock_redis(lock_result=True)
        mock_settings = _make_mock_settings()

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch(
                "src.scheduler.jobs._get_active_accounts",
                return_value=["acc1", "acc2", "acc3"],
            ),
            patch("src.scheduler.jobs._enqueue_ingest_task"),
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        assert mock_redis.aclose.await_count == 1


# ---------------------------------------------------------------------------
# Tests: poll_email_accounts_job — multiple accounts, independent processing
# ---------------------------------------------------------------------------


class TestPollMultipleAccountsIndependent:
    async def test_each_account_gets_separate_lock_key(self) -> None:
        """Lock key is per-account — acc1 and acc2 get distinct Redis keys."""
        mock_redis = _make_mock_redis(lock_result=True)
        mock_settings = _make_mock_settings(
            pipeline_scheduler_lock_key_prefix="mailwise:scheduler:lock"
        )

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch("src.scheduler.jobs._get_active_accounts", return_value=["acc1", "acc2"]),
            patch("src.scheduler.jobs._enqueue_ingest_task"),
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        lock_keys = [call.args[0] for call in mock_redis.set.call_args_list]
        assert "mailwise:scheduler:lock:acc1" in lock_keys
        assert "mailwise:scheduler:lock:acc2" in lock_keys
        assert lock_keys[0] != lock_keys[1]

    async def test_three_accounts_all_processed_independently(self) -> None:
        """All three accounts: acc1 locked, acc2 enqueue fails, acc3 succeeds."""
        mock_redis = AsyncMock()
        # acc1: locked (None), acc2: acquired (True), acc3: acquired (True)
        mock_redis.set.side_effect = [None, True, True]
        mock_redis.delete = AsyncMock(return_value=1)
        mock_redis.aclose = AsyncMock(return_value=None)
        mock_settings = _make_mock_settings()

        enqueued: list[str] = []

        def _enqueue_side_effect(account_id: str, settings: object) -> None:
            if account_id == "acc2":
                raise RuntimeError("enqueue failed for acc2")
            enqueued.append(account_id)

        with (
            patch("src.scheduler.jobs.Redis", _redis_class_patch(mock_redis)),
            patch("src.scheduler.jobs.get_settings", return_value=mock_settings),
            patch(
                "src.scheduler.jobs._get_active_accounts",
                return_value=["acc1", "acc2", "acc3"],
            ),
            patch(
                "src.scheduler.jobs._enqueue_ingest_task",
                side_effect=_enqueue_side_effect,
            ),
        ):
            from src.scheduler.jobs import poll_email_accounts_job

            await poll_email_accounts_job()

        # acc1 skipped (locked), acc2 attempted but failed, acc3 succeeded
        assert enqueued == ["acc3"]
        mock_redis.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: _enqueue_ingest_task — unit tests
# ---------------------------------------------------------------------------


class TestEnqueueIngestTask:
    def test_calls_ingest_task_delay(self) -> None:
        """_enqueue_ingest_task calls ingest_task.delay with account_id and ISO datetime."""
        from src.core.config import Settings

        settings = MagicMock(spec=Settings)
        settings.polling_interval_seconds = 300

        mock_ingest_task = MagicMock()
        mock_task_module = MagicMock()
        mock_task_module.ingest_task = mock_ingest_task

        with patch.dict(
            "sys.modules",
            {"src.tasks.pipeline": mock_task_module},
        ):
            _enqueue_ingest_task("acc-test", settings)

        mock_ingest_task.delay.assert_called_once()

    def test_delay_receives_account_id_as_first_arg(self) -> None:
        """ingest_task.delay first positional arg is the account_id string."""
        from src.core.config import Settings

        settings = MagicMock(spec=Settings)
        settings.polling_interval_seconds = 300

        mock_ingest_task = MagicMock()
        mock_task_module = MagicMock()
        mock_task_module.ingest_task = mock_ingest_task

        with patch.dict(
            "sys.modules",
            {"src.tasks.pipeline": mock_task_module},
        ):
            _enqueue_ingest_task("acc-test-42", settings)

        call_args = mock_ingest_task.delay.call_args
        account_id_arg = call_args.args[0]
        assert account_id_arg == "acc-test-42"

    def test_delay_receives_iso_datetime_string(self) -> None:
        """ingest_task.delay second positional arg is a valid ISO 8601 datetime string."""
        from datetime import UTC, datetime

        from src.core.config import Settings

        settings = MagicMock(spec=Settings)
        settings.polling_interval_seconds = 300

        mock_ingest_task = MagicMock()
        mock_task_module = MagicMock()
        mock_task_module.ingest_task = mock_ingest_task

        with patch.dict(
            "sys.modules",
            {"src.tasks.pipeline": mock_task_module},
        ):
            _enqueue_ingest_task("acc-test", settings)
        after = datetime.now(UTC)

        call_args = mock_ingest_task.delay.call_args
        since_iso = call_args.args[1]

        # Must parse as a valid datetime
        since_dt = datetime.fromisoformat(since_iso)
        # The `since` window starts from `polling_interval_seconds` before call time
        assert since_dt.tzinfo is not None
        assert since_dt <= after

    def test_since_computed_from_polling_interval(self) -> None:
        """since = now() - polling_interval_seconds; longer interval -> earlier timestamp."""
        from datetime import datetime

        from src.core.config import Settings

        settings_short = MagicMock(spec=Settings)
        settings_short.polling_interval_seconds = 60

        settings_long = MagicMock(spec=Settings)
        settings_long.polling_interval_seconds = 600

        results: dict[str, str] = {}
        for label, settings in [("short", settings_short), ("long", settings_long)]:
            mock_ingest_task = MagicMock()
            mock_task_module = MagicMock()
            mock_task_module.ingest_task = mock_ingest_task
            with patch.dict("sys.modules", {"src.tasks.pipeline": mock_task_module}):
                _enqueue_ingest_task("acc-x", settings)
            results[label] = mock_ingest_task.delay.call_args.args[1]

        short_dt = datetime.fromisoformat(results["short"])
        long_dt = datetime.fromisoformat(results["long"])
        # Longer polling_interval -> earlier `since` datetime
        assert long_dt < short_dt

    def test_raises_assertion_error_for_non_settings_object(self) -> None:
        """assert isinstance(settings, Settings) raises for wrong type."""
        not_settings = MagicMock()  # not a real Settings instance

        mock_task_module = MagicMock()
        mock_task_module.ingest_task = MagicMock()

        with (
            patch.dict("sys.modules", {"src.tasks.pipeline": mock_task_module}),
            pytest.raises(AssertionError),
        ):
            _enqueue_ingest_task("acc-test", not_settings)
