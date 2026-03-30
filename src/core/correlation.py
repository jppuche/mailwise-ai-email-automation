"""Correlation ID context for cross-service log tracing.

Uses ``contextvars.ContextVar`` so each async task / coroutine carries
its own correlation ID without thread-local hacks.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="no-correlation")


def set_email_correlation_id(email_id: uuid.UUID) -> None:
    """Set the correlation ID for the current email being processed.

    Called at the start of each pipeline task so all downstream logs
    from the same coroutine / Celery task share one ID.

    Preconditions:
      - email_id is a valid UUID of an Email row in DB.
    External state errors: none — pure ContextVar write.
    Silenced: none.
    """
    _correlation_id.set(str(email_id))


def get_correlation_id() -> str:
    """Return the current correlation ID. Never raises."""
    return _correlation_id.get()
