"""Integration status and connection test router.

Architecture:
  - ZERO try/except — adapter test methods NEVER raise (errors in return value).
  - All endpoints Admin only.
  - Config is read-only from Settings (no PUT endpoints).
  - POST /test always returns 200 — success=False is a valid result.

Endpoints (prefix /api/v1/integrations):
  GET    /email          — Gmail config from Settings (Admin)
  POST   /email/test     — test Gmail connection (Admin)
  GET    /channels       — Slack config from Settings (Admin)
  POST   /channels/test  — test Slack connection (Admin)
  GET    /crm            — HubSpot config from Settings (Admin)
  POST   /crm/test       — test HubSpot connection (Admin)
  GET    /llm            — LLM config from Settings (Admin)
  POST   /llm/test       — test LLM connection (Admin)
"""

from __future__ import annotations

from typing import cast

import structlog
from fastapi import APIRouter, Depends

from src.api.deps import require_admin
from src.api.schemas.integrations import (
    ChannelIntegrationConfig,
    ConnectionTestResult,
    CRMIntegrationConfig,
    EmailIntegrationConfig,
    LLMIntegrationConfig,
)
from src.models.user import User
from src.services.integration_service import IntegrationService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["integrations"])

_integration_service = IntegrationService()


# ============================================================
# Email / Gmail
# ============================================================


@router.get("/email", response_model=EmailIntegrationConfig)
async def get_email_config(
    _current_user: User = Depends(require_admin),  # noqa: B008
) -> EmailIntegrationConfig:
    """Read Gmail integration config from Settings.

    Masks credentials — returns oauth_configured: bool, never the key itself.
    """
    config = _integration_service.get_email_config()
    return EmailIntegrationConfig(
        oauth_configured=bool(config["oauth_configured"]),
        credentials_file=str(config["credentials_file"]),
        token_file=str(config["token_file"]),
        poll_interval_seconds=cast(int, config["poll_interval_seconds"]),
        max_results=cast(int, config["max_results"]),
    )


@router.post("/email/test", response_model=ConnectionTestResult)
async def test_email_connection(
    _current_user: User = Depends(require_admin),  # noqa: B008
) -> ConnectionTestResult:
    """Test Gmail connection. Always returns 200 — success=False is a valid result.

    The adapter test_connection() NEVER raises. All errors captured in result.
    """
    result = await _integration_service.test_email_connection()
    logger.info(
        "integration_test_email",
        success=result["success"],
        latency_ms=result.get("latency_ms"),
    )
    return ConnectionTestResult(
        success=bool(result["success"]),
        latency_ms=result.get("latency_ms") if isinstance(result.get("latency_ms"), int) else None,
        error_detail=result.get("error_detail")
        if isinstance(result.get("error_detail"), str)
        else None,
        adapter_type=str(result["adapter_type"]),
    )


# ============================================================
# Channels / Slack
# ============================================================


@router.get("/channels", response_model=ChannelIntegrationConfig)
async def get_channel_config(
    _current_user: User = Depends(require_admin),  # noqa: B008
) -> ChannelIntegrationConfig:
    """Read Slack integration config from Settings.

    Masks token — returns bot_token_configured: bool, never the token itself.
    """
    config = _integration_service.get_channel_config()
    return ChannelIntegrationConfig(
        bot_token_configured=bool(config["bot_token_configured"]),
        signing_secret_configured=bool(config["signing_secret_configured"]),
        default_channel=str(config["default_channel"]),
        snippet_length=cast(int, config["snippet_length"]),
        timeout_seconds=cast(int, config["timeout_seconds"]),
    )


@router.post("/channels/test", response_model=ConnectionTestResult)
async def test_channel_connection(
    _current_user: User = Depends(require_admin),  # noqa: B008
) -> ConnectionTestResult:
    """Test Slack connection. Always returns 200 — success=False is a valid result."""
    result = await _integration_service.test_channel_connection()
    logger.info(
        "integration_test_channels",
        success=result["success"],
        latency_ms=result.get("latency_ms"),
    )
    return ConnectionTestResult(
        success=bool(result["success"]),
        latency_ms=result.get("latency_ms") if isinstance(result.get("latency_ms"), int) else None,
        error_detail=result.get("error_detail")
        if isinstance(result.get("error_detail"), str)
        else None,
        adapter_type=str(result["adapter_type"]),
    )


# ============================================================
# CRM / HubSpot
# ============================================================


@router.get("/crm", response_model=CRMIntegrationConfig)
async def get_crm_config(
    _current_user: User = Depends(require_admin),  # noqa: B008
) -> CRMIntegrationConfig:
    """Read HubSpot integration config from Settings.

    Masks access token — returns access_token_configured: bool, never the token.
    """
    config = _integration_service.get_crm_config()
    return CRMIntegrationConfig(
        access_token_configured=bool(config["access_token_configured"]),
        auto_create_contacts=bool(config["auto_create_contacts"]),
        default_lead_status=str(config["default_lead_status"]),
        rate_limit_per_10s=cast(int, config["rate_limit_per_10s"]),
        api_timeout_seconds=cast(int, config["api_timeout_seconds"]),
    )


@router.post("/crm/test", response_model=ConnectionTestResult)
async def test_crm_connection(
    _current_user: User = Depends(require_admin),  # noqa: B008
) -> ConnectionTestResult:
    """Test HubSpot connection. Always returns 200 — success=False is a valid result."""
    result = await _integration_service.test_crm_connection()
    logger.info(
        "integration_test_crm",
        success=result["success"],
        latency_ms=result.get("latency_ms"),
    )
    return ConnectionTestResult(
        success=bool(result["success"]),
        latency_ms=result.get("latency_ms") if isinstance(result.get("latency_ms"), int) else None,
        error_detail=result.get("error_detail")
        if isinstance(result.get("error_detail"), str)
        else None,
        adapter_type=str(result["adapter_type"]),
    )


# ============================================================
# LLM
# ============================================================


@router.get("/llm", response_model=LLMIntegrationConfig)
async def get_llm_config(
    _current_user: User = Depends(require_admin),  # noqa: B008
) -> LLMIntegrationConfig:
    """Read LLM integration config from Settings.

    Masks API keys — returns *_api_key_configured: bool, never the key itself.
    """
    config = _integration_service.get_llm_config()
    return LLMIntegrationConfig(
        openai_api_key_configured=bool(config["openai_api_key_configured"]),
        anthropic_api_key_configured=bool(config["anthropic_api_key_configured"]),
        classify_model=str(config["classify_model"]),
        draft_model=str(config["draft_model"]),
        temperature_classify=cast(float, config["temperature_classify"]),
        temperature_draft=cast(float, config["temperature_draft"]),
        fallback_model=str(config["fallback_model"]),
        timeout_seconds=cast(int, config["timeout_seconds"]),
        base_url=str(config["base_url"]),
    )


@router.post("/llm/test", response_model=ConnectionTestResult)
async def test_llm_connection(
    _current_user: User = Depends(require_admin),  # noqa: B008
) -> ConnectionTestResult:
    """Test LLM connection. Always returns 200 — success=False is a valid result."""
    result = await _integration_service.test_llm_connection()
    logger.info(
        "integration_test_llm",
        success=result["success"],
        latency_ms=result.get("latency_ms"),
    )
    return ConnectionTestResult(
        success=bool(result["success"]),
        latency_ms=result.get("latency_ms") if isinstance(result.get("latency_ms"), int) else None,
        error_detail=result.get("error_detail")
        if isinstance(result.get("error_detail"), str)
        else None,
        adapter_type=str(result["adapter_type"]),
    )
