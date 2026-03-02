"""Tests for src/scheduler/main.py — APScheduler entry-point.

Coverage targets:
  1. main(): adds poll_email_accounts_job to scheduler with correct interval
  2. main(): starts scheduler before waiting
  3. main(): asserts lock_ttl >= poll_interval (fail-fast Cat 8)
  4. main(): assertion fails when lock TTL < poll interval
  5. main(): KeyboardInterrupt causes scheduler.shutdown to be called
  6. main(): calls configure_logging with settings values

Architecture:
  - main() is async and uses asyncio.Event().wait() to keep running.
  - Patching asyncio.Event so it immediately raises KeyboardInterrupt or
    returns normally lets us test the shutdown path without blocking.
  - All external calls (scheduler, APScheduler) are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(
    *,
    poll_interval: int = 300,
    lock_ttl: int = 300,
    log_level: str = "INFO",
    log_format: str = "json",
) -> MagicMock:
    settings = MagicMock()
    settings.polling_interval_seconds = poll_interval
    settings.pipeline_scheduler_lock_ttl_seconds = lock_ttl
    settings.log_level = log_level
    settings.log_format = log_format
    return settings


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSchedulerMain:
    """src.scheduler.main.main() entry-point tests."""

    async def test_scheduler_adds_job_and_starts(self) -> None:
        """main() creates scheduler, adds poll job, and calls scheduler.start()."""
        settings = _make_settings(poll_interval=300, lock_ttl=300)
        mock_scheduler = MagicMock()
        mock_scheduler.start = MagicMock()
        mock_scheduler.shutdown = MagicMock()
        mock_event = MagicMock()
        mock_event.wait = AsyncMock(side_effect=KeyboardInterrupt)

        with (
            patch("src.scheduler.main.get_settings", return_value=settings),
            patch("src.core.logging.configure_logging"),
            patch("src.scheduler.main.AsyncIOScheduler", return_value=mock_scheduler),
            patch("src.scheduler.main.asyncio.Event", return_value=mock_event),
        ):
            from src.scheduler.main import main

            await main()

        mock_scheduler.add_job.assert_called_once()
        mock_scheduler.start.assert_called_once()

    async def test_job_added_with_correct_interval(self) -> None:
        """add_job receives IntervalTrigger with poll_interval_seconds."""
        settings = _make_settings(poll_interval=120, lock_ttl=300)
        mock_scheduler = MagicMock()
        mock_event = MagicMock()
        mock_event.wait = AsyncMock(side_effect=KeyboardInterrupt)

        with (
            patch("src.scheduler.main.get_settings", return_value=settings),
            patch("src.core.logging.configure_logging"),
            patch("src.scheduler.main.AsyncIOScheduler", return_value=mock_scheduler),
            patch("src.scheduler.main.IntervalTrigger") as mock_trigger_cls,
            patch("src.scheduler.main.asyncio.Event", return_value=mock_event),
        ):
            from src.scheduler.main import main

            await main()

        mock_trigger_cls.assert_called_once_with(seconds=120)

    async def test_keyboard_interrupt_calls_shutdown(self) -> None:
        """KeyboardInterrupt causes scheduler.shutdown(wait=False)."""
        settings = _make_settings()
        mock_scheduler = MagicMock()
        mock_event = MagicMock()
        mock_event.wait = AsyncMock(side_effect=KeyboardInterrupt)

        with (
            patch("src.scheduler.main.get_settings", return_value=settings),
            patch("src.core.logging.configure_logging"),
            patch("src.scheduler.main.AsyncIOScheduler", return_value=mock_scheduler),
            patch("src.scheduler.main.asyncio.Event", return_value=mock_event),
        ):
            from src.scheduler.main import main

            await main()

        mock_scheduler.shutdown.assert_called_once_with(wait=False)

    async def test_system_exit_calls_shutdown(self) -> None:
        """SystemExit causes scheduler.shutdown(wait=False)."""
        settings = _make_settings()
        mock_scheduler = MagicMock()
        mock_event = MagicMock()
        mock_event.wait = AsyncMock(side_effect=SystemExit(0))

        with (
            patch("src.scheduler.main.get_settings", return_value=settings),
            patch("src.core.logging.configure_logging"),
            patch("src.scheduler.main.AsyncIOScheduler", return_value=mock_scheduler),
            patch("src.scheduler.main.asyncio.Event", return_value=mock_event),
        ):
            from src.scheduler.main import main

            await main()

        mock_scheduler.shutdown.assert_called_once_with(wait=False)

    async def test_lock_ttl_less_than_poll_interval_raises_assertion(self) -> None:
        """Fail-fast Cat 8: assertion fails when lock TTL < poll interval."""
        settings = _make_settings(poll_interval=600, lock_ttl=300)  # TTL < interval

        import pytest

        with (
            patch("src.scheduler.main.get_settings", return_value=settings),
            patch("src.core.logging.configure_logging"),
        ):
            from src.scheduler.main import main

            with pytest.raises(AssertionError, match="Lock TTL"):
                await main()

    async def test_configure_logging_called_with_settings_values(self) -> None:
        """configure_logging receives log_level and log_format from settings."""
        settings = _make_settings(log_level="DEBUG", log_format="text")
        mock_scheduler = MagicMock()
        mock_event = MagicMock()
        mock_event.wait = AsyncMock(side_effect=KeyboardInterrupt)

        with (
            patch("src.scheduler.main.get_settings", return_value=settings),
            patch("src.core.logging.configure_logging") as mock_configure,
            patch("src.scheduler.main.AsyncIOScheduler", return_value=mock_scheduler),
            patch("src.scheduler.main.asyncio.Event", return_value=mock_event),
        ):
            from src.scheduler.main import main

            await main()

        mock_configure.assert_called_once_with(log_level="DEBUG", log_format="text")

    async def test_job_id_is_poll_email_accounts(self) -> None:
        """The scheduled job id is 'poll_email_accounts' (stable for APScheduler)."""
        settings = _make_settings()
        mock_scheduler = MagicMock()
        mock_event = MagicMock()
        mock_event.wait = AsyncMock(side_effect=KeyboardInterrupt)

        with (
            patch("src.scheduler.main.get_settings", return_value=settings),
            patch("src.core.logging.configure_logging"),
            patch("src.scheduler.main.AsyncIOScheduler", return_value=mock_scheduler),
            patch("src.scheduler.main.asyncio.Event", return_value=mock_event),
        ):
            from src.scheduler.main import main

            await main()

        _, add_kwargs = mock_scheduler.add_job.call_args
        assert add_kwargs.get("id") == "poll_email_accounts"
        assert add_kwargs.get("replace_existing") is True

    async def test_normal_exit_when_event_wait_returns(self) -> None:
        """If asyncio.Event().wait() returns normally, shutdown is NOT called."""
        settings = _make_settings()
        mock_scheduler = MagicMock()
        mock_event = MagicMock()
        mock_event.wait = AsyncMock(return_value=None)  # normal exit

        with (
            patch("src.scheduler.main.get_settings", return_value=settings),
            patch("src.core.logging.configure_logging"),
            patch("src.scheduler.main.AsyncIOScheduler", return_value=mock_scheduler),
            patch("src.scheduler.main.asyncio.Event", return_value=mock_event),
        ):
            from src.scheduler.main import main

            await main()

        mock_scheduler.shutdown.assert_not_called()
