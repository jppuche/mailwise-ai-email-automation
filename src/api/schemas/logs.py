"""System log API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LogEntry(BaseModel):
    """Single system log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    timestamp: datetime
    level: str
    source: str
    message: str
    email_id: uuid.UUID | None = None
    context: dict[str, str] = {}


class LogListResponse(BaseModel):
    """Paginated log list."""

    items: list[LogEntry]
    total: int
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)
