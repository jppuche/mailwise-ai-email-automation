"""Integration service — read-only config from Settings + adapter test_connection.

Architecture:
  - Config is read-only (env vars in Settings, not DB-stored).
  - test_connection NEVER raises — all adapter errors become a dict with success=False.
  - EmailAdapter.test_connection() is SYNC — wrap with asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import time

import structlog

from src.core.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class IntegrationService:
    """Read-only integration config + connection testing."""

    def get_email_config(self) -> dict[str, object]:
        """Read Gmail integration config from Settings. Never exposes credentials."""
        settings = get_settings()
        return {
            "oauth_configured": bool(settings.gmail_client_id and settings.gmail_client_secret),
            "credentials_file": settings.gmail_credentials_file,
            "token_file": settings.gmail_token_file,
            "poll_interval_seconds": settings.polling_interval_seconds,
            "max_results": settings.gmail_max_results,
        }

    def get_channel_config(self) -> dict[str, object]:
        """Read Slack integration config from Settings."""
        settings = get_settings()
        return {
            "bot_token_configured": bool(settings.slack_bot_token),
            "signing_secret_configured": bool(settings.slack_signing_secret),
            "default_channel": "",
            "snippet_length": settings.channel_snippet_length,
            "timeout_seconds": settings.channel_slack_timeout_seconds,
        }

    def get_crm_config(self) -> dict[str, object]:
        """Read HubSpot CRM integration config from Settings."""
        settings = get_settings()
        return {
            "access_token_configured": bool(settings.hubspot_access_token),
            "auto_create_contacts": settings.hubspot_auto_create_contacts,
            "default_lead_status": settings.hubspot_default_lead_status,
            "rate_limit_per_10s": settings.hubspot_rate_limit_per_10s,
            "api_timeout_seconds": settings.hubspot_api_timeout_seconds,
        }

    def get_llm_config(self) -> dict[str, object]:
        """Read LLM integration config from Settings."""
        settings = get_settings()
        return {
            "openai_api_key_configured": bool(settings.openai_api_key),
            "anthropic_api_key_configured": bool(settings.anthropic_api_key),
            "classify_model": settings.llm_model_classify,
            "draft_model": settings.llm_model_draft,
            "temperature_classify": settings.llm_temperature_classify,
            "temperature_draft": settings.llm_temperature_draft,
            "fallback_model": settings.llm_fallback_model,
            "timeout_seconds": settings.llm_timeout_seconds,
            "base_url": settings.llm_base_url,
        }

    async def test_email_connection(self) -> dict[str, object]:
        """Test Gmail connection. NEVER raises — errors returned in result dict."""
        start = time.monotonic()
        try:
            from src.adapters.email.gmail import GmailAdapter

            adapter = GmailAdapter()
            # GmailAdapter.test_connection() is SYNC — wrap with asyncio.to_thread
            result = await asyncio.to_thread(adapter.test_connection)
            latency_ms = int((time.monotonic() - start) * 1000)
            return {
                "success": result.connected,
                "latency_ms": latency_ms,
                "error_detail": result.error,
                "adapter_type": "email",
            }
        except Exception as exc:  # noqa: BLE001 — health-check silences ALL errors
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.warning("email_connection_test_failed", error=str(exc))
            return {
                "success": False,
                "latency_ms": latency_ms,
                "error_detail": str(exc),
                "adapter_type": "email",
            }

    async def test_channel_connection(self) -> dict[str, object]:
        """Test Slack connection. NEVER raises."""
        start = time.monotonic()
        try:
            from src.adapters.channel.schemas import ChannelCredentials
            from src.adapters.channel.slack import SlackAdapter

            settings = get_settings()
            adapter = SlackAdapter()
            await adapter.connect(ChannelCredentials(bot_token=settings.slack_bot_token))
            result = await adapter.test_connection()
            latency_ms = int((time.monotonic() - start) * 1000)
            return {
                "success": result.success,
                "latency_ms": latency_ms,
                "error_detail": result.error_detail,
                "adapter_type": "channels",
            }
        except Exception as exc:  # noqa: BLE001 — health-check silences ALL errors
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.warning("channel_connection_test_failed", error=str(exc))
            return {
                "success": False,
                "latency_ms": latency_ms,
                "error_detail": str(exc),
                "adapter_type": "channels",
            }

    async def test_crm_connection(self) -> dict[str, object]:
        """Test HubSpot connection. NEVER raises."""
        start = time.monotonic()
        try:
            from src.adapters.crm.hubspot import HubSpotAdapter
            from src.adapters.crm.schemas import CRMCredentials

            settings = get_settings()
            adapter = HubSpotAdapter()
            await adapter.connect(CRMCredentials(access_token=settings.hubspot_access_token))
            result = await adapter.test_connection()
            latency_ms = int((time.monotonic() - start) * 1000)
            return {
                "success": result.success,
                "latency_ms": latency_ms,
                "error_detail": result.error_detail,
                "adapter_type": "crm",
            }
        except Exception as exc:  # noqa: BLE001 — health-check silences ALL errors
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.warning("crm_connection_test_failed", error=str(exc))
            return {
                "success": False,
                "latency_ms": latency_ms,
                "error_detail": str(exc),
                "adapter_type": "crm",
            }

    async def test_llm_connection(self) -> dict[str, object]:
        """Test LLM connection. NEVER raises."""
        start = time.monotonic()
        try:
            from src.adapters.llm.litellm_adapter import LiteLLMAdapter
            from src.adapters.llm.schemas import LLMConfig

            settings = get_settings()
            config = LLMConfig(
                classify_model=settings.llm_model_classify,
                draft_model=settings.llm_model_draft,
                fallback_model=settings.llm_fallback_model,
                api_key=settings.openai_api_key or None,
                base_url=settings.llm_base_url or None,
                timeout_seconds=settings.llm_timeout_seconds,
            )
            adapter = LiteLLMAdapter(config)
            result = await adapter.test_connection()
            latency_ms = int((time.monotonic() - start) * 1000)
            return {
                "success": result.success,
                "latency_ms": latency_ms,
                "error_detail": result.error_detail,
                "adapter_type": "llm",
            }
        except Exception as exc:  # noqa: BLE001 — health-check silences ALL errors
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.warning("llm_connection_test_failed", error=str(exc))
            return {
                "success": False,
                "latency_ms": latency_ms,
                "error_detail": str(exc),
                "adapter_type": "llm",
            }
