"""Unit tests for GET /api/v1/analytics/* endpoints.

Coverage:
  - TestVolume                    — 200, data format, empty range, reviewer access
  - TestClassificationDistribution — 200, percentage calculation, empty
  - TestAccuracy                  — 200, accuracy_pct formula, zero-classified case
  - TestRoutingStats              — 200, channel data, all-zero empty case
  - TestCsvExport                 — 200 Admin, 403 Reviewer, header row present
  - TestValidation                — 422 on missing / invalid date params
  - TestAuthentication            — 401 on unauthenticated requests

Architecture constraints (D8):
  - Tests use assert conditionals — no try/except in test bodies.
  - _analytics_service patched at module path: src.api.routers.analytics._analytics_service.
  - No real DB or Redis — service is mocked via patch + AsyncMock.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

BASE = "/api/v1/analytics"
_DATE_PARAMS = {"start_date": "2024-01-01", "end_date": "2024-01-31"}
_SERVICE_PATH = "src.api.routers.analytics._analytics_service"


# ---------------------------------------------------------------------------
# TestVolume
# ---------------------------------------------------------------------------


class TestVolume:
    """GET /api/v1/analytics/volume — email volume time series."""

    async def test_admin_receives_200(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin user gets 200 for volume endpoint."""
        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.get_volume = AsyncMock(return_value=([], 0))
            resp = await admin_client.get(f"{BASE}/volume", params=_DATE_PARAMS)

        assert resp.status_code == 200

    async def test_reviewer_receives_200(
        self,
        reviewer_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Reviewer role is authorized for volume endpoint."""
        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.get_volume = AsyncMock(return_value=([], 0))
            resp = await reviewer_client.get(f"{BASE}/volume", params=_DATE_PARAMS)

        assert resp.status_code == 200

    async def test_volume_with_data_returns_correct_data_points(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """data_points list maps service tuples to VolumeDataPoint items."""
        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.get_volume = AsyncMock(
                return_value=(
                    [("2024-01-01", 5), ("2024-01-02", 10)],
                    15,
                )
            )
            resp = await admin_client.get(f"{BASE}/volume", params=_DATE_PARAMS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_emails"] == 15
        assert len(body["data_points"]) == 2
        assert body["data_points"][0]["date"] == "2024-01-01"
        assert body["data_points"][0]["count"] == 5
        assert body["data_points"][1]["date"] == "2024-01-02"
        assert body["data_points"][1]["count"] == 10

    async def test_volume_includes_date_range_in_response(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Response echoes start_date and end_date from query params."""
        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.get_volume = AsyncMock(return_value=([], 0))
            resp = await admin_client.get(f"{BASE}/volume", params=_DATE_PARAMS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["start_date"] == "2024-01-01"
        assert body["end_date"] == "2024-01-31"

    async def test_volume_empty_range_returns_empty_data_points(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Empty period: data_points=[], total_emails=0."""
        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.get_volume = AsyncMock(return_value=([], 0))
            resp = await admin_client.get(f"{BASE}/volume", params=_DATE_PARAMS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["data_points"] == []
        assert body["total_emails"] == 0


# ---------------------------------------------------------------------------
# TestClassificationDistribution
# ---------------------------------------------------------------------------


class TestClassificationDistribution:
    """GET /api/v1/analytics/classification-distribution."""

    async def test_returns_200_with_actions_and_types(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Response includes both actions and types lists."""
        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.get_classification_distribution = AsyncMock(
                return_value=(
                    [("urgent", "Urgent", 8)],
                    [("support", "Support", 8)],
                    8,
                )
            )
            resp = await admin_client.get(
                f"{BASE}/classification-distribution", params=_DATE_PARAMS
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "actions" in body
        assert "types" in body
        assert body["total_classified"] == 8

    async def test_distribution_calculates_percentage(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Percentage is computed from count / total * 100, rounded to 2dp."""
        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.get_classification_distribution = AsyncMock(
                return_value=(
                    [("urgent", "Urgent", 3), ("low", "Low", 1)],
                    [("support", "Support", 4)],
                    4,
                )
            )
            resp = await admin_client.get(
                f"{BASE}/classification-distribution", params=_DATE_PARAMS
            )

        assert resp.status_code == 200
        body = resp.json()
        actions = body["actions"]
        assert len(actions) == 2
        # 3/4 * 100 = 75.0, 1/4 * 100 = 25.0
        assert actions[0]["category"] == "urgent"
        assert actions[0]["display_name"] == "Urgent"
        assert actions[0]["count"] == 3
        assert actions[0]["percentage"] == 75.0
        assert actions[1]["percentage"] == 25.0

    async def test_distribution_empty_returns_zero_lists(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """No classifications: actions=[], types=[], total_classified=0."""
        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.get_classification_distribution = AsyncMock(return_value=([], [], 0))
            resp = await admin_client.get(
                f"{BASE}/classification-distribution", params=_DATE_PARAMS
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["actions"] == []
        assert body["types"] == []
        assert body["total_classified"] == 0


# ---------------------------------------------------------------------------
# TestAccuracy
# ---------------------------------------------------------------------------


class TestAccuracy:
    """GET /api/v1/analytics/accuracy — classification accuracy metric."""

    async def test_returns_200_with_accuracy_fields(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Response contains total_classified, total_overridden, accuracy_pct."""
        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.get_accuracy = AsyncMock(return_value=(100, 10, 90.0))
            resp = await admin_client.get(f"{BASE}/accuracy", params=_DATE_PARAMS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_classified"] == 100
        assert body["total_overridden"] == 10
        assert body["accuracy_pct"] == 90.0

    async def test_accuracy_includes_period_dates(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Response includes period_start and period_end from query params."""
        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.get_accuracy = AsyncMock(return_value=(50, 5, 90.0))
            resp = await admin_client.get(f"{BASE}/accuracy", params=_DATE_PARAMS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["period_start"] == "2024-01-01"
        assert body["period_end"] == "2024-01-31"

    async def test_accuracy_no_classifications_returns_100_pct(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Zero classified emails: accuracy_pct=100.0 (no errors possible)."""
        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.get_accuracy = AsyncMock(return_value=(0, 0, 100.0))
            resp = await admin_client.get(f"{BASE}/accuracy", params=_DATE_PARAMS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_classified"] == 0
        assert body["total_overridden"] == 0
        assert body["accuracy_pct"] == 100.0

    async def test_reviewer_authorized_for_accuracy(
        self,
        reviewer_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Reviewer role can access accuracy endpoint."""
        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.get_accuracy = AsyncMock(return_value=(0, 0, 100.0))
            resp = await reviewer_client.get(f"{BASE}/accuracy", params=_DATE_PARAMS)

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TestRoutingStats
# ---------------------------------------------------------------------------


class TestRoutingStats:
    """GET /api/v1/analytics/routing — per-channel routing statistics."""

    async def test_returns_200_with_channels(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Response contains channels list with dispatched/failed/success_rate."""
        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.get_routing_stats = AsyncMock(
                return_value=(
                    [("slack", 80, 5, 94.12)],
                    80,
                    5,
                    3,
                )
            )
            resp = await admin_client.get(f"{BASE}/routing", params=_DATE_PARAMS)

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["channels"]) == 1
        ch = body["channels"][0]
        assert ch["channel"] == "slack"
        assert ch["dispatched"] == 80
        assert ch["failed"] == 5
        assert ch["success_rate"] == 94.12

    async def test_routing_returns_aggregate_totals(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Response surfaces total_dispatched, total_failed, unrouted_count."""
        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.get_routing_stats = AsyncMock(
                return_value=(
                    [("slack", 40, 2, 95.24), ("hubspot", 30, 3, 90.91)],
                    70,
                    5,
                    12,
                )
            )
            resp = await admin_client.get(f"{BASE}/routing", params=_DATE_PARAMS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_dispatched"] == 70
        assert body["total_failed"] == 5
        assert body["unrouted_count"] == 12

    async def test_routing_empty_returns_zero_counts(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """No routing data: channels=[], all totals=0."""
        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.get_routing_stats = AsyncMock(return_value=([], 0, 0, 0))
            resp = await admin_client.get(f"{BASE}/routing", params=_DATE_PARAMS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["channels"] == []
        assert body["total_dispatched"] == 0
        assert body["total_failed"] == 0
        assert body["unrouted_count"] == 0

    async def test_reviewer_authorized_for_routing(
        self,
        reviewer_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Reviewer role can access routing stats endpoint."""
        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.get_routing_stats = AsyncMock(return_value=([], 0, 0, 0))
            resp = await reviewer_client.get(f"{BASE}/routing", params=_DATE_PARAMS)

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TestCsvExport
# ---------------------------------------------------------------------------


class TestCsvExport:
    """GET /api/v1/analytics/export — CSV streaming (Admin only)."""

    async def test_admin_receives_200_csv_response(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin gets 200 with text/csv content-type."""

        async def _csv_gen() -> object:
            yield "id,received_at,sender_email,subject,state,action_category,type_category\n"

        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.stream_csv_export = MagicMock(return_value=_csv_gen())
            resp = await admin_client.get(f"{BASE}/export", params=_DATE_PARAMS)

        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    async def test_export_has_content_disposition_header(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Response includes Content-Disposition attachment header."""

        async def _csv_gen() -> object:
            yield "id,received_at,sender_email,subject,state,action_category,type_category\n"

        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.stream_csv_export = MagicMock(return_value=_csv_gen())
            resp = await admin_client.get(f"{BASE}/export", params=_DATE_PARAMS)

        assert resp.status_code == 200
        assert "Content-Disposition" in resp.headers
        assert "attachment" in resp.headers["Content-Disposition"]

    async def test_export_first_line_is_csv_header(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """First line of CSV output is the column header row."""
        _header = "id,received_at,sender_email,subject,state,action_category,type_category\n"

        async def _csv_gen() -> object:
            yield _header
            yield (
                'abc,2024-01-01T00:00:00,user@example.com,"Test email",CLASSIFIED,urgent,support\n'
            )

        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.stream_csv_export = MagicMock(return_value=_csv_gen())
            resp = await admin_client.get(f"{BASE}/export", params=_DATE_PARAMS)

        assert resp.status_code == 200
        first_line = resp.text.splitlines()[0]
        assert first_line == _header.rstrip("\n")

    async def test_export_filename_encodes_date_range(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Content-Disposition filename includes start and end dates."""

        async def _csv_gen() -> object:
            yield "id,received_at,sender_email,subject,state,action_category,type_category\n"

        with patch(_SERVICE_PATH) as mock_svc:
            mock_svc.stream_csv_export = MagicMock(return_value=_csv_gen())
            resp = await admin_client.get(f"{BASE}/export", params=_DATE_PARAMS)

        assert resp.status_code == 200
        disposition = resp.headers["Content-Disposition"]
        assert "2024-01-01" in disposition
        assert "2024-01-31" in disposition

    async def test_reviewer_export_returns_403(
        self,
        reviewer_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Reviewer is not authorized for CSV export — 403."""
        resp = await reviewer_client.get(f"{BASE}/export", params=_DATE_PARAMS)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TestValidation
# ---------------------------------------------------------------------------


class TestValidation:
    """Query parameter validation — 422 on bad input."""

    async def test_volume_missing_start_date_returns_422(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """start_date is required — omitting it yields 422."""
        resp = await admin_client.get(f"{BASE}/volume", params={"end_date": "2024-01-31"})
        assert resp.status_code == 422

    async def test_volume_missing_end_date_returns_422(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """end_date is required — omitting it yields 422."""
        resp = await admin_client.get(f"{BASE}/volume", params={"start_date": "2024-01-01"})
        assert resp.status_code == 422

    async def test_volume_invalid_date_format_returns_422(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Malformed date string (not YYYY-MM-DD) yields 422."""
        resp = await admin_client.get(
            f"{BASE}/volume",
            params={"start_date": "01-01-2024", "end_date": "01-31-2024"},
        )
        assert resp.status_code == 422

    async def test_distribution_missing_dates_returns_422(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """classification-distribution also requires both date params."""
        resp = await admin_client.get(f"{BASE}/classification-distribution")
        assert resp.status_code == 422

    async def test_accuracy_missing_dates_returns_422(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """accuracy endpoint requires both date params."""
        resp = await admin_client.get(f"{BASE}/accuracy")
        assert resp.status_code == 422

    async def test_routing_missing_dates_returns_422(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """routing endpoint requires both date params."""
        resp = await admin_client.get(f"{BASE}/routing")
        assert resp.status_code == 422

    async def test_export_missing_dates_returns_422(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """export endpoint requires both date params."""
        resp = await admin_client.get(f"{BASE}/export")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TestAuthentication
# ---------------------------------------------------------------------------


class TestAuthentication:
    """Unauthenticated requests must return 401 on all analytics endpoints."""

    async def test_volume_unauthenticated_returns_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """No auth token → 401 on volume endpoint."""
        resp = await unauthenticated_client.get(f"{BASE}/volume", params=_DATE_PARAMS)
        assert resp.status_code == 401

    async def test_distribution_unauthenticated_returns_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """No auth token → 401 on classification-distribution endpoint."""
        resp = await unauthenticated_client.get(
            f"{BASE}/classification-distribution", params=_DATE_PARAMS
        )
        assert resp.status_code == 401

    async def test_accuracy_unauthenticated_returns_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """No auth token → 401 on accuracy endpoint."""
        resp = await unauthenticated_client.get(f"{BASE}/accuracy", params=_DATE_PARAMS)
        assert resp.status_code == 401

    async def test_routing_unauthenticated_returns_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """No auth token → 401 on routing endpoint."""
        resp = await unauthenticated_client.get(f"{BASE}/routing", params=_DATE_PARAMS)
        assert resp.status_code == 401

    async def test_export_unauthenticated_returns_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """No auth token → 401 on export endpoint."""
        resp = await unauthenticated_client.get(f"{BASE}/export", params=_DATE_PARAMS)
        assert resp.status_code == 401
