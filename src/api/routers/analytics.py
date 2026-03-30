"""Analytics router — SQL aggregation queries + CSV export.

Architecture:
  - ZERO try/except — domain exceptions propagate to exception_handlers.py.
  - Reviewer+ for dashboard views, Admin for CSV export.
  - All aggregation in SQL — zero Python loops over email lists.
  - CSV export uses StreamingResponse with AsyncGenerator.

Endpoints (prefix /api/v1/analytics):
  GET /volume                      — email volume time series (Reviewer+)
  GET /classification-distribution — action/type pie charts (Reviewer+)
  GET /accuracy                    — classification accuracy % (Reviewer+)
  GET /routing                     — routing channel stats (Reviewer+)
  GET /export                      — CSV streaming export (Admin only)
"""

from __future__ import annotations

from datetime import date

import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import require_admin, require_reviewer_or_admin
from src.api.schemas.analytics import (
    AccuracyResponse,
    ClassificationDistributionResponse,
    DistributionItem,
    RoutingChannelStat,
    RoutingResponse,
    VolumeDataPoint,
    VolumeResponse,
)
from src.core.database import get_async_db
from src.models.user import User
from src.services.analytics_service import AnalyticsService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["analytics"])

_analytics_service = AnalyticsService()


@router.get("/volume", response_model=VolumeResponse)
async def get_volume(
    start_date: date = Query(...),  # noqa: B008
    end_date: date = Query(...),  # noqa: B008
    _current_user: User = Depends(require_reviewer_or_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> VolumeResponse:
    """Email volume time series — GROUP BY day.

    Returns daily email counts for the given date range.
    Raises ValueError if range exceeds analytics_max_date_range_days.
    """
    data_points, total = await _analytics_service.get_volume(start_date, end_date, db)
    return VolumeResponse(
        data_points=[VolumeDataPoint(date=dp, count=cnt) for dp, cnt in data_points],
        total_emails=total,
        start_date=str(start_date),
        end_date=str(end_date),
    )


@router.get("/classification-distribution", response_model=ClassificationDistributionResponse)
async def get_classification_distribution(
    start_date: date = Query(...),  # noqa: B008
    end_date: date = Query(...),  # noqa: B008
    _current_user: User = Depends(require_reviewer_or_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> ClassificationDistributionResponse:
    """Classification distribution — action and type breakdown.

    Returns per-category counts and percentages for the given date range.
    """
    actions_raw, types_raw, total = await _analytics_service.get_classification_distribution(
        start_date, end_date, db
    )

    def _to_items(rows: list[tuple[str, str, int]], row_total: int) -> list[DistributionItem]:
        return [
            DistributionItem(
                category=slug,
                display_name=name,
                count=count,
                percentage=round(count / row_total * 100, 2) if row_total > 0 else 0.0,
            )
            for slug, name, count in rows
        ]

    return ClassificationDistributionResponse(
        actions=_to_items(actions_raw, total),
        types=_to_items(types_raw, total),
        total_classified=total,
    )


@router.get("/accuracy", response_model=AccuracyResponse)
async def get_accuracy(
    start_date: date = Query(...),  # noqa: B008
    end_date: date = Query(...),  # noqa: B008
    _current_user: User = Depends(require_reviewer_or_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> AccuracyResponse:
    """Classification accuracy based on feedback overrides.

    accuracy_pct = (1 - overridden/classified) * 100.
    Returns 100.0 if no emails were classified in the period.
    """
    total_classified, total_overridden, accuracy_pct = await _analytics_service.get_accuracy(
        start_date, end_date, db
    )
    return AccuracyResponse(
        total_classified=total_classified,
        total_overridden=total_overridden,
        accuracy_pct=accuracy_pct,
        period_start=str(start_date),
        period_end=str(end_date),
    )


@router.get("/routing", response_model=RoutingResponse)
async def get_routing_stats(
    start_date: date = Query(...),  # noqa: B008
    end_date: date = Query(...),  # noqa: B008
    _current_user: User = Depends(require_reviewer_or_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> RoutingResponse:
    """Routing channel statistics — dispatched, failed, success rate per channel.

    Includes unrouted_count: emails with no matching routing action.
    """
    (
        channels_raw,
        total_dispatched,
        total_failed,
        unrouted,
    ) = await _analytics_service.get_routing_stats(start_date, end_date, db)
    channels = [
        RoutingChannelStat(
            channel=ch,
            dispatched=dispatched,
            failed=failed,
            success_rate=success_rate,
        )
        for ch, dispatched, failed, success_rate in channels_raw
    ]
    return RoutingResponse(
        channels=channels,
        total_dispatched=total_dispatched,
        total_failed=total_failed,
        unrouted_count=unrouted,
    )


@router.get("/export")
async def export_csv(
    start_date: date = Query(...),  # noqa: B008
    end_date: date = Query(...),  # noqa: B008
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> StreamingResponse:
    """CSV streaming export of emails in date range. Admin only.

    Streams chunked rows — never loads all emails into memory.
    Content-Disposition: attachment; filename=emails_YYYY-MM-DD_YYYY-MM-DD.csv
    """
    generator = _analytics_service.stream_csv_export(start_date, end_date, db)
    filename = f"emails_{start_date}_{end_date}.csv"
    return StreamingResponse(
        generator,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
