"""Tests for IntegrationService — mocked adapters and Settings.

Coverage targets:
  1. get_email_config: returns dict with expected keys
  2. get_channel_config: returns dict with expected keys
  3. get_crm_config: returns dict with expected keys
  4. get_llm_config: returns dict with expected keys
  5. test_email_connection: adapter.test_connection succeeds → success=True
  6. test_email_connection: adapter raises Exception → success=False, no raise
  7. test_channel_connection: adapter succeeds → success=True
  8. test_channel_connection: adapter raises Exception → success=False, no raise
  9. test_crm_connection: adapter succeeds → success=True
 10. test_crm_connection: adapter raises Exception → success=False, no raise
 11. test_llm_connection: adapter succeeds → success=True
 12. test_llm_connection: adapter raises Exception → success=False, no raise

Architecture note:
  - test_* methods NEVER raise (all errors returned in dict with success=False).
  - test_email_connection wraps sync adapter with asyncio.to_thread.
  - Settings injected via monkeypatched get_settings.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from src.services.integration_service import IntegrationService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(
    *,
    gmail_client_id: str = "",
    gmail_client_secret: str = "",
    gmail_credentials_file: str = "secrets/creds.json",
    gmail_token_file: str = "secrets/token.json",
    polling_interval_seconds: int = 300,
    gmail_max_results: int = 100,
    slack_bot_token: str = "",
    slack_signing_secret: str = "",
    channel_snippet_length: int = 150,
    channel_slack_timeout_seconds: int = 10,
    hubspot_access_token: str = "",
    hubspot_auto_create_contacts: bool = False,
    hubspot_default_lead_status: str = "NEW",
    hubspot_rate_limit_per_10s: int = 100,
    hubspot_api_timeout_seconds: int = 15,
    openai_api_key: str = "",
    anthropic_api_key: str = "",
    llm_model_classify: str = "gpt-4o-mini",
    llm_model_draft: str = "gpt-4o",
    llm_temperature_classify: float = 0.1,
    llm_temperature_draft: float = 0.7,
    llm_fallback_model: str = "gpt-3.5-turbo",
    llm_timeout_seconds: int = 30,
    llm_base_url: str = "",
) -> MagicMock:
    settings = MagicMock()
    settings.gmail_client_id = gmail_client_id
    settings.gmail_client_secret = gmail_client_secret
    settings.gmail_credentials_file = gmail_credentials_file
    settings.gmail_token_file = gmail_token_file
    settings.polling_interval_seconds = polling_interval_seconds
    settings.gmail_max_results = gmail_max_results
    settings.slack_bot_token = slack_bot_token
    settings.slack_signing_secret = slack_signing_secret
    settings.channel_snippet_length = channel_snippet_length
    settings.channel_slack_timeout_seconds = channel_slack_timeout_seconds
    settings.hubspot_access_token = hubspot_access_token
    settings.hubspot_auto_create_contacts = hubspot_auto_create_contacts
    settings.hubspot_default_lead_status = hubspot_default_lead_status
    settings.hubspot_rate_limit_per_10s = hubspot_rate_limit_per_10s
    settings.hubspot_api_timeout_seconds = hubspot_api_timeout_seconds
    settings.openai_api_key = openai_api_key
    settings.anthropic_api_key = anthropic_api_key
    settings.llm_model_classify = llm_model_classify
    settings.llm_model_draft = llm_model_draft
    settings.llm_temperature_classify = llm_temperature_classify
    settings.llm_temperature_draft = llm_temperature_draft
    settings.llm_fallback_model = llm_fallback_model
    settings.llm_timeout_seconds = llm_timeout_seconds
    settings.llm_base_url = llm_base_url
    return settings


# ---------------------------------------------------------------------------
# TestGetEmailConfig
# ---------------------------------------------------------------------------


class TestGetEmailConfig:
    def test_returns_expected_keys(self) -> None:
        service = IntegrationService()
        settings = _make_settings(gmail_client_id="client-id", gmail_client_secret="secret")

        with patch("src.services.integration_service.get_settings", return_value=settings):
            config = service.get_email_config()

        assert "oauth_configured" in config
        assert "credentials_file" in config
        assert "token_file" in config
        assert "poll_interval_seconds" in config
        assert "max_results" in config

    def test_oauth_configured_true_when_both_creds_set(self) -> None:
        service = IntegrationService()
        settings = _make_settings(gmail_client_id="cid", gmail_client_secret="csec")

        with patch("src.services.integration_service.get_settings", return_value=settings):
            config = service.get_email_config()

        assert config["oauth_configured"] is True

    def test_oauth_configured_false_when_creds_missing(self) -> None:
        service = IntegrationService()
        settings = _make_settings(gmail_client_id="", gmail_client_secret="")

        with patch("src.services.integration_service.get_settings", return_value=settings):
            config = service.get_email_config()

        assert config["oauth_configured"] is False


# ---------------------------------------------------------------------------
# TestGetChannelConfig
# ---------------------------------------------------------------------------


class TestGetChannelConfig:
    def test_returns_expected_keys(self) -> None:
        service = IntegrationService()
        settings = _make_settings()

        with patch("src.services.integration_service.get_settings", return_value=settings):
            config = service.get_channel_config()

        assert "bot_token_configured" in config
        assert "signing_secret_configured" in config
        assert "snippet_length" in config
        assert "timeout_seconds" in config

    def test_bot_token_configured_true_when_set(self) -> None:
        service = IntegrationService()
        settings = _make_settings(slack_bot_token="xoxb-token")

        with patch("src.services.integration_service.get_settings", return_value=settings):
            config = service.get_channel_config()

        assert config["bot_token_configured"] is True


# ---------------------------------------------------------------------------
# TestGetCrmConfig
# ---------------------------------------------------------------------------


class TestGetCrmConfig:
    def test_returns_expected_keys(self) -> None:
        service = IntegrationService()
        settings = _make_settings()

        with patch("src.services.integration_service.get_settings", return_value=settings):
            config = service.get_crm_config()

        assert "access_token_configured" in config
        assert "auto_create_contacts" in config
        assert "default_lead_status" in config
        assert "rate_limit_per_10s" in config

    def test_access_token_configured_false_when_empty(self) -> None:
        service = IntegrationService()
        settings = _make_settings(hubspot_access_token="")

        with patch("src.services.integration_service.get_settings", return_value=settings):
            config = service.get_crm_config()

        assert config["access_token_configured"] is False


# ---------------------------------------------------------------------------
# TestGetLlmConfig
# ---------------------------------------------------------------------------


class TestGetLlmConfig:
    def test_returns_expected_keys(self) -> None:
        service = IntegrationService()
        settings = _make_settings()

        with patch("src.services.integration_service.get_settings", return_value=settings):
            config = service.get_llm_config()

        assert "openai_api_key_configured" in config
        assert "anthropic_api_key_configured" in config
        assert "classify_model" in config
        assert "draft_model" in config
        assert "fallback_model" in config

    def test_openai_key_configured_true_when_set(self) -> None:
        service = IntegrationService()
        settings = _make_settings(openai_api_key="sk-test")

        with patch("src.services.integration_service.get_settings", return_value=settings):
            config = service.get_llm_config()

        assert config["openai_api_key_configured"] is True


# ---------------------------------------------------------------------------
# TestTestEmailConnection
# ---------------------------------------------------------------------------


class TestTestEmailConnection:
    async def test_success_returns_success_true(self) -> None:
        """When adapter.test_connection succeeds, result has success=True."""
        service = IntegrationService()

        connection_result = MagicMock()
        connection_result.connected = True
        connection_result.error = None

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = connection_result

        with (
            patch(
                "src.services.integration_service.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value=connection_result,
            ),
            patch(
                "src.services.integration_service.IntegrationService.test_email_connection",
                wraps=service.test_email_connection,
            ),
        ):
            # Patch the deferred import path
            import sys

            mock_gmail_module = MagicMock()
            mock_gmail_module.GmailAdapter.return_value = mock_adapter

            with patch.dict(sys.modules, {"src.adapters.email.gmail": mock_gmail_module}):
                # We patch asyncio.to_thread to return the mock result directly
                async def fake_to_thread(func: object, *args: object) -> object:
                    return connection_result

                with patch("src.services.integration_service.asyncio.to_thread", fake_to_thread):
                    result = await service.test_email_connection()

        assert result["success"] is True
        assert result["adapter_type"] == "email"

    async def test_exception_returns_success_false_no_raise(self) -> None:
        """Any exception from adapter returns success=False, does not propagate."""
        service = IntegrationService()

        import sys

        mock_gmail_module = MagicMock()
        mock_gmail_module.GmailAdapter.side_effect = RuntimeError("adapter failed")

        with patch.dict(sys.modules, {"src.adapters.email.gmail": mock_gmail_module}):
            result = await service.test_email_connection()

        assert result["success"] is False
        assert result["adapter_type"] == "email"
        assert "error_detail" in result


# ---------------------------------------------------------------------------
# TestTestChannelConnection
# ---------------------------------------------------------------------------


class TestTestChannelConnection:
    async def test_success_returns_success_true(self) -> None:
        """Slack adapter test_connection succeeds → success=True."""
        service = IntegrationService()

        test_result = MagicMock()
        test_result.success = True
        test_result.error_detail = None

        mock_adapter = AsyncMock()
        mock_adapter.connect = AsyncMock()
        mock_adapter.test_connection = AsyncMock(return_value=test_result)

        import sys

        mock_slack_module = MagicMock()
        mock_slack_module.SlackAdapter.return_value = mock_adapter

        mock_schemas_module = MagicMock()

        settings = _make_settings(slack_bot_token="xoxb-token")

        with (
            patch.dict(
                sys.modules,
                {
                    "src.adapters.channel.slack": mock_slack_module,
                    "src.adapters.channel.schemas": mock_schemas_module,
                },
            ),
            patch("src.services.integration_service.get_settings", return_value=settings),
        ):
            result = await service.test_channel_connection()

        assert result["success"] is True
        assert result["adapter_type"] == "channels"

    async def test_exception_returns_success_false(self) -> None:
        """Exception from Slack adapter returns success=False, no raise."""
        service = IntegrationService()

        import sys

        mock_slack_module = MagicMock()
        mock_slack_module.SlackAdapter.side_effect = ConnectionError("slack down")
        mock_schemas_module = MagicMock()

        settings = _make_settings()

        with (
            patch.dict(
                sys.modules,
                {
                    "src.adapters.channel.slack": mock_slack_module,
                    "src.adapters.channel.schemas": mock_schemas_module,
                },
            ),
            patch("src.services.integration_service.get_settings", return_value=settings),
        ):
            result = await service.test_channel_connection()

        assert result["success"] is False
        assert result["adapter_type"] == "channels"


# ---------------------------------------------------------------------------
# TestTestCrmConnection
# ---------------------------------------------------------------------------


class TestTestCrmConnection:
    async def test_success_returns_success_true(self) -> None:
        """HubSpot adapter test_connection succeeds → success=True."""
        service = IntegrationService()

        test_result = MagicMock()
        test_result.success = True
        test_result.error_detail = None

        mock_adapter = AsyncMock()
        mock_adapter.connect = AsyncMock()
        mock_adapter.test_connection = AsyncMock(return_value=test_result)

        import sys

        mock_hubspot_module = MagicMock()
        mock_hubspot_module.HubSpotAdapter.return_value = mock_adapter

        mock_crm_schemas = MagicMock()
        settings = _make_settings(hubspot_access_token="token-123")

        with (
            patch.dict(
                sys.modules,
                {
                    "src.adapters.crm.hubspot": mock_hubspot_module,
                    "src.adapters.crm.schemas": mock_crm_schemas,
                },
            ),
            patch("src.services.integration_service.get_settings", return_value=settings),
        ):
            result = await service.test_crm_connection()

        assert result["success"] is True
        assert result["adapter_type"] == "crm"

    async def test_exception_returns_success_false(self) -> None:
        """Exception from HubSpot adapter returns success=False, no raise."""
        service = IntegrationService()

        import sys

        mock_hubspot_module = MagicMock()
        mock_hubspot_module.HubSpotAdapter.side_effect = RuntimeError("hubspot down")
        mock_crm_schemas = MagicMock()

        settings = _make_settings()

        with (
            patch.dict(
                sys.modules,
                {
                    "src.adapters.crm.hubspot": mock_hubspot_module,
                    "src.adapters.crm.schemas": mock_crm_schemas,
                },
            ),
            patch("src.services.integration_service.get_settings", return_value=settings),
        ):
            result = await service.test_crm_connection()

        assert result["success"] is False
        assert result["adapter_type"] == "crm"


# ---------------------------------------------------------------------------
# TestTestLlmConnection
# ---------------------------------------------------------------------------


class TestTestLlmConnection:
    async def test_success_returns_success_true(self) -> None:
        """LLM adapter test_connection succeeds → success=True."""
        service = IntegrationService()

        test_result = MagicMock()
        test_result.success = True
        test_result.error_detail = None

        mock_adapter = AsyncMock()
        mock_adapter.test_connection = AsyncMock(return_value=test_result)

        import sys

        mock_litellm_module = MagicMock()
        mock_litellm_module.LiteLLMAdapter.return_value = mock_adapter

        mock_llm_schemas = MagicMock()
        mock_llm_schemas.LLMConfig.return_value = MagicMock()

        settings = _make_settings(openai_api_key="sk-key")

        with (
            patch.dict(
                sys.modules,
                {
                    "src.adapters.llm.litellm_adapter": mock_litellm_module,
                    "src.adapters.llm.schemas": mock_llm_schemas,
                },
            ),
            patch("src.services.integration_service.get_settings", return_value=settings),
        ):
            result = await service.test_llm_connection()

        assert result["success"] is True
        assert result["adapter_type"] == "llm"

    async def test_exception_returns_success_false(self) -> None:
        """Exception from LLM adapter returns success=False, no raise."""
        service = IntegrationService()

        import sys

        mock_litellm_module = MagicMock()
        mock_litellm_module.LiteLLMAdapter.side_effect = RuntimeError("llm down")
        mock_llm_schemas = MagicMock()
        mock_llm_schemas.LLMConfig.return_value = MagicMock()

        settings = _make_settings()

        with (
            patch.dict(
                sys.modules,
                {
                    "src.adapters.llm.litellm_adapter": mock_litellm_module,
                    "src.adapters.llm.schemas": mock_llm_schemas,
                },
            ),
            patch("src.services.integration_service.get_settings", return_value=settings),
        ):
            result = await service.test_llm_connection()

        assert result["success"] is False
        assert result["adapter_type"] == "llm"
