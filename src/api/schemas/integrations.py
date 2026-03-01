"""Integration status and connection test schemas."""

from __future__ import annotations

from pydantic import BaseModel


class EmailIntegrationConfig(BaseModel):
    """Gmail integration config — read-only from Settings. Never exposes credentials."""

    oauth_configured: bool
    credentials_file: str
    token_file: str
    poll_interval_seconds: int
    max_results: int


class ChannelIntegrationConfig(BaseModel):
    """Slack integration config — read-only from Settings."""

    bot_token_configured: bool
    signing_secret_configured: bool
    default_channel: str
    snippet_length: int
    timeout_seconds: int


class CRMIntegrationConfig(BaseModel):
    """HubSpot CRM integration config — read-only from Settings."""

    access_token_configured: bool
    auto_create_contacts: bool
    default_lead_status: str
    rate_limit_per_10s: int
    api_timeout_seconds: int


class LLMIntegrationConfig(BaseModel):
    """LLM integration config — read-only from Settings."""

    openai_api_key_configured: bool
    anthropic_api_key_configured: bool
    classify_model: str
    draft_model: str
    temperature_classify: float
    temperature_draft: float
    fallback_model: str
    timeout_seconds: int
    base_url: str


class ConnectionTestResult(BaseModel):
    """Result of POST /test. Always 200 OK — success=False is a valid result."""

    success: bool
    latency_ms: int | None = None
    error_detail: str | None = None
    adapter_type: str
