"""Analytics API schemas — volume, distribution, accuracy, routing."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class DateRangeFilter(BaseModel):
    """Query parameters for analytics endpoints."""

    start_date: date
    end_date: date

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info: object) -> date:
        if hasattr(info, "data") and "start_date" in info.data and v < info.data["start_date"]:
            raise ValueError("end_date must be >= start_date")
        return v


class VolumeDataPoint(BaseModel):
    """Single data point in the volume time series."""

    date: str  # "YYYY-MM-DD" — no datetime to avoid tz ambiguity in JSON
    count: int


class VolumeResponse(BaseModel):
    """Email volume time series response."""

    data_points: list[VolumeDataPoint]
    total_emails: int
    start_date: str
    end_date: str


class DistributionItem(BaseModel):
    """Single bucket in a classification distribution."""

    category: str
    display_name: str
    count: int
    percentage: float


class ClassificationDistributionResponse(BaseModel):
    """Classification distribution — action and type pie charts."""

    actions: list[DistributionItem]
    types: list[DistributionItem]
    total_classified: int


class AccuracyResponse(BaseModel):
    """Classification accuracy — based on feedback overrides."""

    total_classified: int
    total_overridden: int
    accuracy_pct: float  # (1 - overridden/classified) * 100
    period_start: str
    period_end: str


class RoutingChannelStat(BaseModel):
    """Stats for a single routing channel."""

    channel: str
    dispatched: int
    failed: int
    success_rate: float


class RoutingResponse(BaseModel):
    """Routing statistics response."""

    channels: list[RoutingChannelStat]
    total_dispatched: int
    total_failed: int
    unrouted_count: int


class ExportFormat(BaseModel):
    """Query parameter for CSV export format selection."""

    format: str = Field(default="csv", pattern="^csv$")
