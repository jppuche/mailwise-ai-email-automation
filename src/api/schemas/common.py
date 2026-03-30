"""Common API schemas — pagination, errors, health."""

from pydantic import BaseModel, Field


class PaginatedResponse[T](BaseModel):
    """Paginated list response. Generic over item type T."""

    items: list[T]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    pages: int = Field(ge=0)


class ErrorResponse(BaseModel):
    """Standardized error response body."""

    error: str
    message: str
    detail: str | None = None


class AdapterHealthItem(BaseModel):
    """Health status of a single adapter."""

    name: str
    status: str
    latency_ms: int | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Aggregated health check response."""

    status: str
    version: str
    adapters: list[AdapterHealthItem]
