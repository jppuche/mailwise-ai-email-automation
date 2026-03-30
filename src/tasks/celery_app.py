"""Celery application instance and configuration.

Broker: Redis/0, result backend: Redis/1 (separated to avoid namespace
interference between task messages and result metadata).

All values sourced from Settings — no hardcoded defaults.
JSON serializer only — no pickle (security).
"""

from __future__ import annotations

from celery import Celery

from src.core.config import get_settings


def _create_celery_app() -> Celery:
    """Build and configure the Celery application from Settings.

    Guarantees:
      - broker_url and result_backend come from env-configurable Settings.
      - JSON serializer for safety (no pickle).
      - UTC timezone.
      - Result expiration set via ``celery_result_expires``.
      - Autodiscovers tasks from ``src.tasks``.
    """
    settings = get_settings()

    app = Celery("mailwise")

    app.conf.update(
        broker_url=settings.celery_broker_url,
        result_backend=settings.celery_result_backend,
        result_expires=settings.celery_result_expires,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
    )

    app.autodiscover_tasks(["src.tasks"])

    return app


celery_app = _create_celery_app()

from celery.signals import worker_init  # noqa: E402


@worker_init.connect  # type: ignore[untyped-decorator]
def _on_worker_init(**kwargs: object) -> None:
    """Configure structured logging when the Celery worker boots."""
    from src.core.logging import configure_logging

    settings = get_settings()
    configure_logging(
        log_level=settings.log_level,
        log_format=settings.log_format,
    )
