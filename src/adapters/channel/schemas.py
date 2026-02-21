"""Adapter-boundary data contracts for channel operations.

tighten-types D1: No ``dict[str, Any]`` in any public type.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SenderInfo(BaseModel):
    """Sender information embedded in the routing payload."""

    email: str
    name: str | None = None


class ClassificationInfo(BaseModel):
    """Classification result embedded in the routing payload."""

    action: str
    type: str
    confidence: Literal["high", "low"]


class RoutingPayload(BaseModel):
    """Canonical routing notification payload (FOUNDATION.md Sec 5.4).

    Consumed by Slack formatter and any future channel adapters.
    """

    email_id: str
    subject: str
    sender: SenderInfo
    classification: ClassificationInfo
    priority: Literal["urgent", "normal", "low"]
    snippet: str
    dashboard_link: str
    assigned_to: str | None = None
    timestamp: datetime


class Destination(BaseModel):
    """Channel or user target in the channel adapter."""

    id: str  # Slack channel ID (C...) or user ID (U...)
    name: str  # readable name (#general, @john)
    type: Literal["channel", "dm", "group"]


class ChannelCredentials(BaseModel):
    """Credentials for connecting to a channel adapter."""

    bot_token: str  # xoxb-... for Slack


class ConnectionStatus(BaseModel):
    """Result of a connect() call."""

    connected: bool
    workspace_name: str | None = None
    bot_user_id: str | None = None
    error: str | None = None


class ConnectionTestResult(BaseModel):
    """Result of a test_connection() health check."""

    success: bool
    workspace_name: str | None = None
    latency_ms: int
    error_detail: str | None = None


class DeliveryResult(BaseModel):
    """Result of a send_notification() call."""

    success: bool
    message_ts: str | None = None  # Slack message timestamp (for thread replies)
    channel_id: str | None = None
    error_detail: str | None = None
