"""Analytics service — SQL aggregation queries + CSV streaming.

Architecture:
  - All aggregation via SQL GROUP BY — zero Python loops over email lists.
  - CSV export via AsyncGenerator + StreamingResponse.
  - Email.date is the received_at column.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import date
from typing import cast

import structlog
from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.models.category import ActionCategory, TypeCategory
from src.models.classification import ClassificationResult
from src.models.email import Email
from src.models.feedback import ClassificationFeedback
from src.models.routing import RoutingAction, RoutingActionStatus

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class AnalyticsService:
    """SQL-based analytics — no Python aggregation loops."""

    async def get_volume(
        self,
        start_date: date,
        end_date: date,
        db: AsyncSession,
    ) -> tuple[list[tuple[str, int]], int]:
        """Email volume time series — GROUP BY day.

        Returns (data_points, total) where data_points is list of (date_str, count).
        """
        settings = get_settings()
        delta = (end_date - start_date).days
        if delta > settings.analytics_max_date_range_days:
            raise ValueError(
                f"Date range exceeds maximum of {settings.analytics_max_date_range_days} days"
            )

        stmt = (
            select(
                func.date_trunc("day", Email.date).label("day"),
                func.count(Email.id).label("count"),
            )
            .where(Email.date >= start_date, Email.date <= end_date)
            .group_by(text("day"))
            .order_by(text("day"))
        )
        result = await db.execute(stmt)
        rows = result.all()

        data_points = [(str(row.day.date()), cast(int, row._mapping["count"])) for row in rows]
        total = sum(count for _, count in data_points)
        return data_points, total

    async def get_classification_distribution(
        self,
        start_date: date,
        end_date: date,
        db: AsyncSession,
    ) -> tuple[list[tuple[str, str, int]], list[tuple[str, str, int]], int]:
        """Classification distribution — action and type breakdown.

        Returns (actions, types, total_classified).
        Each list item is (slug, display_name, count).
        """
        # Action distribution
        action_stmt = (
            select(
                ActionCategory.slug,
                ActionCategory.name,
                func.count(ClassificationResult.id).label("count"),
            )
            .join(ActionCategory, ClassificationResult.action_category_id == ActionCategory.id)
            .join(Email, ClassificationResult.email_id == Email.id)
            .where(Email.date >= start_date, Email.date <= end_date)
            .group_by(ActionCategory.slug, ActionCategory.name)
            .order_by(text("count DESC"))
        )
        action_result = await db.execute(action_stmt)
        actions = [
            (row.slug, row.name, cast(int, row._mapping["count"])) for row in action_result.all()
        ]

        # Type distribution
        type_stmt = (
            select(
                TypeCategory.slug,
                TypeCategory.name,
                func.count(ClassificationResult.id).label("count"),
            )
            .join(TypeCategory, ClassificationResult.type_category_id == TypeCategory.id)
            .join(Email, ClassificationResult.email_id == Email.id)
            .where(Email.date >= start_date, Email.date <= end_date)
            .group_by(TypeCategory.slug, TypeCategory.name)
            .order_by(text("count DESC"))
        )
        type_result = await db.execute(type_stmt)
        types = [
            (row.slug, row.name, cast(int, row._mapping["count"])) for row in type_result.all()
        ]

        total = sum(count for _, _, count in actions)
        return actions, types, total

    async def get_accuracy(
        self,
        start_date: date,
        end_date: date,
        db: AsyncSession,
    ) -> tuple[int, int, float]:
        """Classification accuracy — based on feedback overrides.

        Returns (total_classified, total_overridden, accuracy_pct).
        accuracy_pct = (1 - overridden/classified) * 100.
        """
        # Total classified in period
        classified_stmt = (
            select(func.count(ClassificationResult.id))
            .join(Email, ClassificationResult.email_id == Email.id)
            .where(Email.date >= start_date, Email.date <= end_date)
        )
        classified_result = await db.execute(classified_stmt)
        total_classified: int = classified_result.scalar_one() or 0

        # Total overridden in period
        overridden_stmt = (
            select(func.count(ClassificationFeedback.id))
            .join(Email, ClassificationFeedback.email_id == Email.id)
            .where(Email.date >= start_date, Email.date <= end_date)
        )
        overridden_result = await db.execute(overridden_stmt)
        total_overridden: int = overridden_result.scalar_one() or 0

        if total_classified == 0:
            accuracy_pct = 100.0
        else:
            accuracy_pct = round((1 - total_overridden / total_classified) * 100, 2)

        return total_classified, total_overridden, accuracy_pct

    async def get_routing_stats(
        self,
        start_date: date,
        end_date: date,
        db: AsyncSession,
    ) -> tuple[list[tuple[str, int, int, float]], int, int, int]:
        """Routing channel statistics.

        Returns (channels, total_dispatched, total_failed, unrouted_count).
        Each channel item is (channel_name, dispatched, failed, success_rate).
        """
        # Per-channel stats
        channel_stmt = (
            select(
                RoutingAction.channel,
                func.count(
                    case(
                        (RoutingAction.status == RoutingActionStatus.DISPATCHED, 1),
                    )
                ).label("dispatched"),
                func.count(
                    case(
                        (RoutingAction.status == RoutingActionStatus.FAILED, 1),
                    )
                ).label("failed"),
            )
            .join(Email, RoutingAction.email_id == Email.id)
            .where(Email.date >= start_date, Email.date <= end_date)
            .group_by(RoutingAction.channel)
        )
        channel_result = await db.execute(channel_stmt)
        channels_raw = channel_result.all()

        channels: list[tuple[str, int, int, float]] = []
        total_dispatched = 0
        total_failed = 0
        for row in channels_raw:
            d: int = row.dispatched
            f: int = row.failed
            rate = round(d / (d + f) * 100, 2) if (d + f) > 0 else 0.0
            channels.append((row.channel, d, f, rate))
            total_dispatched += d
            total_failed += f

        # Unrouted: emails in date range with no RoutingAction
        unrouted_stmt = (
            select(func.count(Email.id))
            .outerjoin(RoutingAction, RoutingAction.email_id == Email.id)
            .where(Email.date >= start_date, Email.date <= end_date)
            .where(RoutingAction.id.is_(None))
        )
        unrouted_result = await db.execute(unrouted_stmt)
        unrouted_count: int = unrouted_result.scalar_one() or 0

        return channels, total_dispatched, total_failed, unrouted_count

    async def stream_csv_export(
        self,
        start_date: date,
        end_date: date,
        db: AsyncSession,
    ) -> AsyncGenerator[str, None]:
        """CSV export — streaming generator with chunked DB reads.

        Yields CSV rows without loading all emails into memory.
        """
        settings = get_settings()
        chunk_size = settings.analytics_csv_chunk_size

        yield "id,received_at,sender_email,subject,state,action_category,type_category\n"

        offset = 0
        while True:
            stmt = (
                select(
                    Email.id,
                    Email.date,
                    Email.sender_email,
                    Email.subject,
                    Email.state,
                    ActionCategory.slug.label("action_slug"),
                    TypeCategory.slug.label("type_slug"),
                )
                .outerjoin(ClassificationResult, ClassificationResult.email_id == Email.id)
                .outerjoin(
                    ActionCategory,
                    ClassificationResult.action_category_id == ActionCategory.id,
                )
                .outerjoin(
                    TypeCategory,
                    ClassificationResult.type_category_id == TypeCategory.id,
                )
                .where(Email.date >= start_date, Email.date <= end_date)
                .order_by(Email.date)
                .offset(offset)
                .limit(chunk_size)
            )
            result = await db.execute(stmt)
            rows = result.all()
            if not rows:
                break

            for row in rows:
                # Escape CSV fields containing commas or quotes
                subject = str(row.subject or "").replace('"', '""')
                sender = str(row.sender_email or "")
                action = row.action_slug or ""
                type_ = row.type_slug or ""
                yield (
                    f'{row.id},{row.date.isoformat()},{sender},"{subject}"'
                    f",{row.state.value},{action},{type_}\n"
                )

            offset += chunk_size
