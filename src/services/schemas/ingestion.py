"""Ingestion pipeline data contracts.

These types are the output of IngestionService — fully typed, immutable
results that describe what happened to each email during ingestion.

tighten-types D1: No ``dict[str, Any]`` at boundaries.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class SkipReason(StrEnum):
    """Why an email was skipped during ingestion (not an error)."""

    DUPLICATE = "DUPLICATE"
    THREAD_NOT_NEWEST = "THREAD_NOT_NEWEST"


class FailureReason(StrEnum):
    """Why an email failed during ingestion (operational error)."""

    DB_WRITE_ERROR = "DB_WRITE_ERROR"
    DB_TRANSITION_ERROR = "DB_TRANSITION_ERROR"


@dataclass(frozen=True)
class IngestionResult:
    """Outcome of processing a single email.

    Invariants:
      - Exactly one of ``email_id``, ``skip_reason``, ``failure_reason`` is set.
      - ``provider_message_id`` is always populated.

    Guarantees:
      - Immutable after creation (frozen dataclass).
    """

    provider_message_id: str
    email_id: uuid.UUID | None = None
    skip_reason: SkipReason | None = None
    failure_reason: FailureReason | None = None
    error_detail: str | None = None

    @property
    def is_ingested(self) -> bool:
        return (
            self.email_id is not None and self.skip_reason is None and self.failure_reason is None
        )

    @property
    def is_skipped(self) -> bool:
        return self.skip_reason is not None

    @property
    def is_failed(self) -> bool:
        return self.failure_reason is not None


@dataclass
class IngestionBatchResult:
    """Aggregate result of a batch ingestion run.

    Not frozen — built incrementally as each email is processed.

    Invariants:
      - ``account_id`` is always populated.
      - ``results`` may be empty (empty batch or lock not acquired).

    Guarantees:
      - ``ingested + skipped + failed == len(results)``.
      - ``lock_acquired`` is False when another worker holds the lock.
    """

    account_id: str
    lock_acquired: bool = True
    results: list[IngestionResult] = field(default_factory=list)

    @property
    def ingested(self) -> int:
        return sum(1 for r in self.results if r.is_ingested)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.is_skipped)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.is_failed)
