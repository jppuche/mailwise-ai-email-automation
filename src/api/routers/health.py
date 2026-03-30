"""Health check router — aggregated adapter health.

Architecture:
  - GET /health: always HTTP 200 (never 503).
  - "degraded" if any adapter fails or times out.
  - Adapters checked in parallel via asyncio.gather.
  - Configurable timeout (default 200ms).
  - ONLY place in routers/ with try/except (by design).
"""

import asyncio
import time

import structlog
from fastapi import APIRouter

from src.api.schemas.common import AdapterHealthItem, HealthResponse
from src.core.config import get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Aggregated health check. Always HTTP 200."""
    settings = get_settings()
    timeout_s = settings.api_health_adapter_timeout_ms / 1000.0

    results = await asyncio.gather(
        _check_db(timeout_s),
        _check_redis(timeout_s),
        return_exceptions=True,
    )

    adapters: list[AdapterHealthItem] = []
    for item in results:
        if isinstance(item, AdapterHealthItem):
            adapters.append(item)
        else:
            adapters.append(
                AdapterHealthItem(name="unknown", status="unavailable", error=str(item))
            )

    overall = "ok" if all(a.status == "ok" for a in adapters) else "degraded"
    return HealthResponse(status=overall, version=settings.app_version, adapters=adapters)


async def _check_db(timeout_s: float) -> AdapterHealthItem:
    """Check PostgreSQL connectivity."""
    start = time.monotonic()
    try:
        from sqlalchemy import text

        from src.core.database import async_engine

        async with async_engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=timeout_s)
        latency = int((time.monotonic() - start) * 1000)
        return AdapterHealthItem(name="database", status="ok", latency_ms=latency)
    except TimeoutError:
        return AdapterHealthItem(name="database", status="degraded", error="timeout")
    except Exception as exc:  # noqa: BLE001
        return AdapterHealthItem(name="database", status="unavailable", error=str(exc))


async def _check_redis(timeout_s: float) -> AdapterHealthItem:
    """Check Redis connectivity."""
    start = time.monotonic()
    try:
        from src.adapters.redis_client import _get_redis

        client = await asyncio.wait_for(_get_redis(), timeout=timeout_s)
        await asyncio.wait_for(client.ping(), timeout=timeout_s)
        latency = int((time.monotonic() - start) * 1000)
        return AdapterHealthItem(name="redis", status="ok", latency_ms=latency)
    except TimeoutError:
        return AdapterHealthItem(name="redis", status="degraded", error="timeout")
    except Exception as exc:  # noqa: BLE001
        return AdapterHealthItem(name="redis", status="unavailable", error=str(exc))
