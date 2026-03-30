"""Tests for AnalyticsService — mocked AsyncSession.

Coverage targets:
  1. get_volume: happy path returns (data_points, total)
  2. get_volume: date range exceeds max raises ValueError
  3. get_volume: empty result returns empty list and total=0
  4. get_classification_distribution: happy path with actions + types
  5. get_classification_distribution: empty result returns empty lists
  6. get_accuracy: zero classified returns 100.0 accuracy
  7. get_accuracy: non-zero classified returns ratio
  8. get_routing_stats: channels with dispatched + failed rows
  9. get_routing_stats: empty channels returns empty list and unrouted count
 10. stream_csv_export: yields header + rows then stops at empty chunk
 11. stream_csv_export: yields header when no rows on first page

Mocking strategy:
  - AsyncSession: AsyncMock with execute.return_value chained via side_effect.
  - Row objects: MagicMock() with named attributes to simulate SQLAlchemy rows.
  - Settings: monkeypatched get_settings.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.analytics_service import AnalyticsService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


def _make_settings(
    *,
    max_date_range_days: int = 365,
    csv_chunk_size: int = 100,
) -> MagicMock:
    settings = MagicMock()
    settings.analytics_max_date_range_days = max_date_range_days
    settings.analytics_csv_chunk_size = csv_chunk_size
    return settings


def _make_result_with_rows(rows: list[object]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


def _make_scalar_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one.return_value = value
    result.scalar_one_or_none.return_value = value
    return result


# ---------------------------------------------------------------------------
# TestGetVolume
# ---------------------------------------------------------------------------


class TestGetVolume:
    """AnalyticsService.get_volume — email volume time series."""

    async def test_happy_path_returns_data_points_and_total(self) -> None:
        """get_volume returns sorted data_points and sum total."""
        db = _make_db()
        service = AnalyticsService()

        # One day row
        row = MagicMock()
        row.day = MagicMock()
        row.day.date.return_value = date(2026, 1, 15)
        row._mapping = {"count": 5}

        db.execute.return_value = _make_result_with_rows([row])

        with patch("src.services.analytics_service.get_settings", return_value=_make_settings()):
            data_points, total = await service.get_volume(date(2026, 1, 1), date(2026, 1, 31), db)

        assert len(data_points) == 1
        assert data_points[0][1] == 5
        assert total == 5

    async def test_empty_result_returns_empty_list_and_zero_total(self) -> None:
        """When no rows exist in range, returns ([], 0)."""
        db = _make_db()
        service = AnalyticsService()
        db.execute.return_value = _make_result_with_rows([])

        with patch("src.services.analytics_service.get_settings", return_value=_make_settings()):
            data_points, total = await service.get_volume(date(2026, 1, 1), date(2026, 1, 2), db)

        assert data_points == []
        assert total == 0

    async def test_date_range_exceeds_max_raises_value_error(self) -> None:
        """Date range longer than analytics_max_date_range_days raises ValueError."""
        db = _make_db()
        service = AnalyticsService()
        settings = _make_settings(max_date_range_days=10)

        with (
            patch("src.services.analytics_service.get_settings", return_value=settings),
            pytest.raises(ValueError, match="Date range exceeds maximum"),
        ):
            await service.get_volume(date(2026, 1, 1), date(2026, 3, 1), db)

    async def test_multiple_rows_sum_total(self) -> None:
        """Total equals sum of all day counts."""
        db = _make_db()
        service = AnalyticsService()

        rows = []
        for i, count in enumerate([3, 7, 10]):
            row = MagicMock()
            row.day = MagicMock()
            row.day.date.return_value = date(2026, 1, i + 1)
            row._mapping = {"count": count}
            rows.append(row)

        db.execute.return_value = _make_result_with_rows(rows)

        with patch("src.services.analytics_service.get_settings", return_value=_make_settings()):
            _, total = await service.get_volume(date(2026, 1, 1), date(2026, 1, 31), db)

        assert total == 20


# ---------------------------------------------------------------------------
# TestGetClassificationDistribution
# ---------------------------------------------------------------------------


class TestGetClassificationDistribution:
    """AnalyticsService.get_classification_distribution."""

    async def test_happy_path_returns_actions_types_and_total(self) -> None:
        """Returns (actions, types, total_classified) with correct data."""
        db = _make_db()
        service = AnalyticsService()

        action_row = MagicMock()
        action_row.slug = "respond"
        action_row.name = "Respond"
        action_row._mapping = {"count": 12}

        type_row = MagicMock()
        type_row.slug = "support"
        type_row.name = "Support"
        type_row._mapping = {"count": 8}

        db.execute.side_effect = [
            _make_result_with_rows([action_row]),
            _make_result_with_rows([type_row]),
        ]

        with patch("src.services.analytics_service.get_settings", return_value=_make_settings()):
            actions, types, total = await service.get_classification_distribution(
                date(2026, 1, 1), date(2026, 1, 31), db
            )

        assert len(actions) == 1
        assert actions[0] == ("respond", "Respond", 12)
        assert len(types) == 1
        assert types[0] == ("support", "Support", 8)
        assert total == 12

    async def test_empty_returns_empty_lists_and_zero(self) -> None:
        """No classifications in range returns ([], [], 0)."""
        db = _make_db()
        service = AnalyticsService()

        db.execute.side_effect = [
            _make_result_with_rows([]),
            _make_result_with_rows([]),
        ]

        with patch("src.services.analytics_service.get_settings", return_value=_make_settings()):
            actions, types, total = await service.get_classification_distribution(
                date(2026, 1, 1), date(2026, 1, 31), db
            )

        assert actions == []
        assert types == []
        assert total == 0


# ---------------------------------------------------------------------------
# TestGetAccuracy
# ---------------------------------------------------------------------------


class TestGetAccuracy:
    """AnalyticsService.get_accuracy — classification accuracy from feedback."""

    async def test_zero_classified_returns_100_pct(self) -> None:
        """When no emails were classified, accuracy_pct is 100.0."""
        db = _make_db()
        service = AnalyticsService()

        db.execute.side_effect = [
            _make_scalar_result(0),  # total_classified
            _make_scalar_result(0),  # total_overridden
        ]

        with patch("src.services.analytics_service.get_settings", return_value=_make_settings()):
            total_classified, total_overridden, accuracy_pct = await service.get_accuracy(
                date(2026, 1, 1), date(2026, 1, 31), db
            )

        assert total_classified == 0
        assert total_overridden == 0
        assert accuracy_pct == 100.0

    async def test_some_overridden_returns_ratio(self) -> None:
        """5 overridden out of 100 classified = 95.0% accuracy."""
        db = _make_db()
        service = AnalyticsService()

        db.execute.side_effect = [
            _make_scalar_result(100),
            _make_scalar_result(5),
        ]

        with patch("src.services.analytics_service.get_settings", return_value=_make_settings()):
            total_classified, total_overridden, accuracy_pct = await service.get_accuracy(
                date(2026, 1, 1), date(2026, 1, 31), db
            )

        assert total_classified == 100
        assert total_overridden == 5
        assert accuracy_pct == pytest.approx(95.0)

    async def test_all_overridden_returns_zero_pct(self) -> None:
        """All 10 classified and overridden = 0.0% accuracy."""
        db = _make_db()
        service = AnalyticsService()

        db.execute.side_effect = [
            _make_scalar_result(10),
            _make_scalar_result(10),
        ]

        with patch("src.services.analytics_service.get_settings", return_value=_make_settings()):
            _, _, accuracy_pct = await service.get_accuracy(date(2026, 1, 1), date(2026, 1, 31), db)

        assert accuracy_pct == 0.0

    async def test_none_scalar_treated_as_zero(self) -> None:
        """scalar_one() returns None → treated as 0, accuracy 100.0."""
        db = _make_db()
        service = AnalyticsService()

        # simulate scalar_one returning None (no rows)
        r1 = MagicMock()
        r1.scalar_one.return_value = None
        r2 = MagicMock()
        r2.scalar_one.return_value = None
        db.execute.side_effect = [r1, r2]

        with patch("src.services.analytics_service.get_settings", return_value=_make_settings()):
            total_classified, _, accuracy_pct = await service.get_accuracy(
                date(2026, 1, 1), date(2026, 1, 31), db
            )

        assert total_classified == 0
        assert accuracy_pct == 100.0


# ---------------------------------------------------------------------------
# TestGetRoutingStats
# ---------------------------------------------------------------------------


class TestGetRoutingStats:
    """AnalyticsService.get_routing_stats — routing channel statistics."""

    async def test_happy_path_returns_channels_and_counts(self) -> None:
        """Returns (channels, total_dispatched, total_failed, unrouted_count)."""
        db = _make_db()
        service = AnalyticsService()

        channel_row = MagicMock()
        channel_row.channel = "slack"
        channel_row.dispatched = 8
        channel_row.failed = 2

        unrouted_result = _make_scalar_result(3)

        db.execute.side_effect = [
            _make_result_with_rows([channel_row]),
            unrouted_result,
        ]

        with patch("src.services.analytics_service.get_settings", return_value=_make_settings()):
            (
                channels,
                total_dispatched,
                total_failed,
                unrouted_count,
            ) = await service.get_routing_stats(date(2026, 1, 1), date(2026, 1, 31), db)

        assert len(channels) == 1
        assert channels[0][0] == "slack"
        assert channels[0][1] == 8  # dispatched
        assert channels[0][2] == 2  # failed
        assert channels[0][3] == pytest.approx(80.0)  # success_rate
        assert total_dispatched == 8
        assert total_failed == 2
        assert unrouted_count == 3

    async def test_empty_channels_returns_zeros(self) -> None:
        """No routing actions returns ([], 0, 0, unrouted_count)."""
        db = _make_db()
        service = AnalyticsService()

        db.execute.side_effect = [
            _make_result_with_rows([]),
            _make_scalar_result(5),
        ]

        with patch("src.services.analytics_service.get_settings", return_value=_make_settings()):
            (
                channels,
                total_dispatched,
                total_failed,
                unrouted_count,
            ) = await service.get_routing_stats(date(2026, 1, 1), date(2026, 1, 31), db)

        assert channels == []
        assert total_dispatched == 0
        assert total_failed == 0
        assert unrouted_count == 5

    async def test_zero_dispatched_and_failed_success_rate_is_zero(self) -> None:
        """When dispatched + failed == 0, success_rate is 0.0 (no ZeroDivisionError)."""
        db = _make_db()
        service = AnalyticsService()

        channel_row = MagicMock()
        channel_row.channel = "slack"
        channel_row.dispatched = 0
        channel_row.failed = 0

        db.execute.side_effect = [
            _make_result_with_rows([channel_row]),
            _make_scalar_result(0),
        ]

        with patch("src.services.analytics_service.get_settings", return_value=_make_settings()):
            channels, _, _, _ = await service.get_routing_stats(
                date(2026, 1, 1), date(2026, 1, 31), db
            )

        assert channels[0][3] == 0.0


# ---------------------------------------------------------------------------
# TestStreamCsvExport
# ---------------------------------------------------------------------------


class TestStreamCsvExport:
    """AnalyticsService.stream_csv_export — streaming CSV generator."""

    async def test_yields_header_line_first(self) -> None:
        """First yielded value is the CSV header line."""
        db = _make_db()
        service = AnalyticsService()

        # First call returns empty — stop immediately
        db.execute.return_value = _make_result_with_rows([])

        with patch("src.services.analytics_service.get_settings", return_value=_make_settings()):
            gen = service.stream_csv_export(date(2026, 1, 1), date(2026, 1, 31), db)
            first = await gen.__anext__()

        assert "id" in first
        assert "received_at" in first
        assert "subject" in first

    async def test_yields_header_then_stops_when_no_rows(self) -> None:
        """When first query returns no rows, only header is yielded."""
        db = _make_db()
        service = AnalyticsService()
        db.execute.return_value = _make_result_with_rows([])

        with patch("src.services.analytics_service.get_settings", return_value=_make_settings()):
            rows_collected = []
            async for row in service.stream_csv_export(date(2026, 1, 1), date(2026, 1, 31), db):
                rows_collected.append(row)

        assert len(rows_collected) == 1  # only the header

    async def test_yields_data_rows_for_emails(self) -> None:
        """Data rows are yielded after header for each email in result."""
        db = _make_db()
        service = AnalyticsService()

        row = MagicMock()
        row.id = "email-001"
        row.date = MagicMock()
        row.date.isoformat.return_value = "2026-01-15T10:00:00"
        row.sender_email = "sender@example.com"
        row.subject = "Hello"
        row.state = MagicMock()
        row.state.value = "CLASSIFIED"
        row.action_slug = "respond"
        row.type_slug = "support"

        # First call returns one row, second call returns empty (stop)
        db.execute.side_effect = [
            _make_result_with_rows([row]),
            _make_result_with_rows([]),
        ]

        with patch(
            "src.services.analytics_service.get_settings",
            return_value=_make_settings(csv_chunk_size=1),
        ):
            rows_collected = []
            async for chunk in service.stream_csv_export(date(2026, 1, 1), date(2026, 1, 31), db):
                rows_collected.append(chunk)

        # Header + 1 data row
        assert len(rows_collected) == 2
        assert "email-001" in rows_collected[1]

    async def test_quotes_in_subject_are_escaped(self) -> None:
        """Subjects containing double-quotes are escaped as double-double-quotes in CSV."""
        db = _make_db()
        service = AnalyticsService()

        row = MagicMock()
        row.id = "email-002"
        row.date = MagicMock()
        row.date.isoformat.return_value = "2026-01-15T10:00:00"
        row.sender_email = "sender@example.com"
        row.subject = 'Hello "World"'
        row.state = MagicMock()
        row.state.value = "CLASSIFIED"
        row.action_slug = None
        row.type_slug = None

        db.execute.side_effect = [
            _make_result_with_rows([row]),
            _make_result_with_rows([]),
        ]

        with patch(
            "src.services.analytics_service.get_settings",
            return_value=_make_settings(csv_chunk_size=1),
        ):
            rows_collected = []
            async for chunk in service.stream_csv_export(date(2026, 1, 1), date(2026, 1, 31), db):
                rows_collected.append(chunk)

        # escaped as ""
        data_row = rows_collected[1]
        assert '""' in data_row
