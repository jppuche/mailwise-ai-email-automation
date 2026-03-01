"""System logs router — paginated filtered log viewer.

Architecture:
  - ZERO try/except — domain exceptions propagate to exception_handlers.py.
  - Admin only.
  - Query SystemLog model directly — simple enough, no service layer.

Endpoints (prefix /api/v1/logs):
  GET / — paginated, filtered system log list (Admin)
"""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import require_admin
from src.api.schemas.logs import LogEntry, LogListResponse
from src.core.database import get_async_db
from src.models.system_log import SystemLog
from src.models.user import User

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["logs"])


@router.get("/", response_model=LogListResponse)
async def list_logs(
    level: str | None = Query(default=None),  # noqa: B008
    source: str | None = Query(default=None),  # noqa: B008
    since: datetime | None = Query(default=None),  # noqa: B008
    until: datetime | None = Query(default=None),  # noqa: B008
    email_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    offset: int = Query(default=0, ge=0),  # noqa: B008
    _current_user: User = Depends(require_admin),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> LogListResponse:
    """Paginated filtered system log list. Admin only.

    Filters: level, source, since, until, email_id.
    Default limit: 50. Max: 200.
    Ordered by timestamp descending.
    """
    from sqlalchemy import func

    base_q = select(SystemLog)

    if level is not None:
        base_q = base_q.where(SystemLog.level == level)
    if source is not None:
        base_q = base_q.where(SystemLog.source == source)
    if since is not None:
        base_q = base_q.where(SystemLog.timestamp >= since)
    if until is not None:
        base_q = base_q.where(SystemLog.timestamp <= until)
    if email_id is not None:
        base_q = base_q.where(SystemLog.email_id == email_id)

    # Total count
    count_q = select(func.count()).select_from(base_q.subquery())
    total_result = await db.execute(count_q)
    total: int = total_result.scalar_one()

    # Paginated fetch ordered by timestamp descending
    page_q = base_q.order_by(SystemLog.timestamp.desc()).offset(offset).limit(limit)
    logs_result = await db.execute(page_q)
    logs = list(logs_result.scalars().all())

    items = [
        LogEntry(
            id=log.id,
            timestamp=log.timestamp,
            level=log.level,
            source=log.source,
            message=log.message,
            email_id=log.email_id,
            context=log.context,
        )
        for log in logs
    ]

    return LogListResponse(items=items, total=total, limit=limit, offset=offset)
