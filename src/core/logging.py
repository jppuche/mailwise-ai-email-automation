"""Structured JSON logging for all mailwise processes.

Provides ``configure_logging()`` which must be called once in each
entry-point process:
  - ``src/api/main.py``         (lifespan startup)
  - ``src/tasks/celery_app.py`` (``worker_init`` signal)
  - ``src/scheduler/main.py``   (before ``scheduler.start()``)

PII policy (last-line defence):
  ``PiiSanitizingFilter`` redacts prohibited field names from log
  event dicts. Primary PII prevention lives in services — this is
  the safety net.

``LOG_FORMAT``:
  - ``json``  -> ``structlog.processors.JSONRenderer()`` (default / prod)
  - ``text``  -> ``structlog.dev.ConsoleRenderer()``     (local dev)
"""

from __future__ import annotations

import logging
import logging.config
from collections.abc import MutableMapping
from typing import Any

import structlog

from src.core.correlation import get_correlation_id

# Fields that MUST NEVER appear in log output (PII / email content).
_PII_FIELDS: frozenset[str] = frozenset(
    {
        "subject",
        "from_address",
        "body_plain",
        "body_html",
        "sender_name",
        "recipient_address",
        "sender_email",
    }
)

_REDACTED = "[REDACTED]"


def _add_correlation_id(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Inject ``correlation_id`` from the current ContextVar."""
    event_dict.setdefault("correlation_id", get_correlation_id())
    return event_dict


def _sanitize_pii(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Redact top-level keys that match PII field names.

    Only scans top-level event-dict keys — nested dicts are NOT
    traversed to minimise false positives (Option B from handoff).
    """
    for key in _PII_FIELDS:
        if key in event_dict:
            event_dict[key] = _REDACTED
    return event_dict


def configure_logging(
    log_level: str = "INFO",
    log_format: str = "json",
) -> None:
    """Configure structured logging for the current process.

    Parameters
    ----------
    log_level:
        Python log level name (DEBUG, INFO, WARNING, ERROR).
    log_format:
        ``json`` for production (JSONRenderer) or ``text`` for
        local development (ConsoleRenderer).
    """
    renderer: structlog.types.Processor
    if log_format.lower() == "text":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _add_correlation_id,
            _sanitize_pii,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper(), logging.INFO),
        force=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a named structured logger.

    Usage: ``logger = get_logger(__name__)``
    Always bind ``email_id`` for email-related operations — never
    subject / sender / body.
    """
    return structlog.get_logger(name)  # type: ignore[no-any-return]
