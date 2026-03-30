"""Unit tests for /api/v1/integrations/* endpoints.

Coverage:
  - TestGetEmailConfig        — 200 fields, 403 reviewer, no credentials in response
  - TestGetChannelConfig      — 200 fields, 403 reviewer, no credentials in response
  - TestGetCRMConfig          — 200 fields, 403 reviewer, no credentials in response
  - TestGetLLMConfig          — 200 fields, 403 reviewer, no credentials in response
  - TestTestEmailConnection   — success=True, success=False, 403 reviewer
  - TestTestChannelConnection — success=True, success=False
  - TestTestCRMConnection     — success=True, success=False
  - TestTestLLMConnection     — success=True, success=False
  - TestAuthGuards            — 401 unauthenticated, 403 reviewer for every endpoint

Architecture constraints (D8):
  - Tests use assert conditionals — no try/except.
  - _integration_service patched at module level in the router.
  - POST /test always 200 — success=False is a valid result.
  - Critical security invariant: no raw credential values in any response.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

BASE = "/api/v1/integrations"

# Sentinel values used to detect credential leakage — never appear in responses.
_FORBIDDEN_KEYS = frozenset({"api_key", "token", "password", "secret", "access_token"})


# ---------------------------------------------------------------------------
# Helpers — service return values
# ---------------------------------------------------------------------------


def _email_config() -> dict[str, object]:
    return {
        "oauth_configured": True,
        "credentials_file": "secrets/gmail_credentials.json",
        "token_file": "secrets/gmail_token.json",
        "poll_interval_seconds": 300,
        "max_results": 50,
    }


def _channel_config() -> dict[str, object]:
    return {
        "bot_token_configured": True,
        "signing_secret_configured": False,
        "default_channel": "#alerts",
        "snippet_length": 200,
        "timeout_seconds": 10,
    }


def _crm_config() -> dict[str, object]:
    return {
        "access_token_configured": True,
        "auto_create_contacts": True,
        "default_lead_status": "NEW",
        "rate_limit_per_10s": 9,
        "api_timeout_seconds": 30,
    }


def _llm_config() -> dict[str, object]:
    return {
        "openai_api_key_configured": True,
        "anthropic_api_key_configured": False,
        "classify_model": "gpt-4o-mini",
        "draft_model": "gpt-4o",
        "temperature_classify": 0.1,
        "temperature_draft": 0.7,
        "fallback_model": "gpt-3.5-turbo",
        "timeout_seconds": 30,
        "base_url": "https://api.openai.com/v1",
    }


def _connection_success(adapter_type: str) -> dict[str, object]:
    return {
        "success": True,
        "latency_ms": 42,
        "error_detail": None,
        "adapter_type": adapter_type,
    }


def _connection_failure(adapter_type: str, error: str = "connection refused") -> dict[str, object]:
    return {
        "success": False,
        "latency_ms": 15,
        "error_detail": error,
        "adapter_type": adapter_type,
    }


def _make_mock_service(
    *,
    email_cfg: dict[str, object] | None = None,
    channel_cfg: dict[str, object] | None = None,
    crm_cfg: dict[str, object] | None = None,
    llm_cfg: dict[str, object] | None = None,
    email_test: dict[str, object] | None = None,
    channel_test: dict[str, object] | None = None,
    crm_test: dict[str, object] | None = None,
    llm_test: dict[str, object] | None = None,
) -> MagicMock:
    """Return a fully-configured mock IntegrationService."""
    svc = MagicMock()
    svc.get_email_config.return_value = email_cfg or _email_config()
    svc.get_channel_config.return_value = channel_cfg or _channel_config()
    svc.get_crm_config.return_value = crm_cfg or _crm_config()
    svc.get_llm_config.return_value = llm_cfg or _llm_config()
    svc.test_email_connection = AsyncMock(return_value=email_test or _connection_success("email"))
    svc.test_channel_connection = AsyncMock(
        return_value=channel_test or _connection_success("channels")
    )
    svc.test_crm_connection = AsyncMock(return_value=crm_test or _connection_success("crm"))
    svc.test_llm_connection = AsyncMock(return_value=llm_test or _connection_success("llm"))
    return svc


# ---------------------------------------------------------------------------
# Security helper
# ---------------------------------------------------------------------------


def _assert_no_raw_credentials(body: dict[str, object]) -> None:
    """Assert that no raw credential value appears as a key in the response body."""
    for key in body:
        assert key not in _FORBIDDEN_KEYS, (
            f"Response body exposes raw credential key '{key}'. "
            "Only *_configured: bool fields are permitted."
        )


# ---------------------------------------------------------------------------
# TestGetEmailConfig
# ---------------------------------------------------------------------------


class TestGetEmailConfig:
    """GET /api/v1/integrations/email — Gmail config (Admin only)."""

    async def test_admin_receives_200_with_email_config_fields(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Admin receives 200 with all EmailIntegrationConfig fields present."""
        svc = _make_mock_service()

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.get(f"{BASE}/email")

        assert resp.status_code == 200
        body = resp.json()
        assert body["oauth_configured"] is True
        assert body["credentials_file"] == "secrets/gmail_credentials.json"
        assert body["token_file"] == "secrets/gmail_token.json"
        assert body["poll_interval_seconds"] == 300
        assert body["max_results"] == 50

    async def test_reviewer_receives_403(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer is not authorized for the integrations namespace — 403."""
        resp = await reviewer_client.get(f"{BASE}/email")
        assert resp.status_code == 403

    async def test_no_raw_credentials_in_email_config(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Response must not expose api_key, token, password, or secret fields."""
        svc = _make_mock_service()

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.get(f"{BASE}/email")

        assert resp.status_code == 200
        _assert_no_raw_credentials(resp.json())

    async def test_oauth_configured_false_when_unconfigured(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """oauth_configured=False surfaces correctly when credentials are absent."""
        cfg = _email_config()
        cfg["oauth_configured"] = False
        svc = _make_mock_service(email_cfg=cfg)

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.get(f"{BASE}/email")

        assert resp.status_code == 200
        assert resp.json()["oauth_configured"] is False


# ---------------------------------------------------------------------------
# TestGetChannelConfig
# ---------------------------------------------------------------------------


class TestGetChannelConfig:
    """GET /api/v1/integrations/channels — Slack config (Admin only)."""

    async def test_admin_receives_200_with_channel_config_fields(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Admin receives 200 with all ChannelIntegrationConfig fields present."""
        svc = _make_mock_service()

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.get(f"{BASE}/channels")

        assert resp.status_code == 200
        body = resp.json()
        assert body["bot_token_configured"] is True
        assert body["signing_secret_configured"] is False
        assert body["default_channel"] == "#alerts"
        assert body["snippet_length"] == 200
        assert body["timeout_seconds"] == 10

    async def test_reviewer_receives_403(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer is not authorized — 403."""
        resp = await reviewer_client.get(f"{BASE}/channels")
        assert resp.status_code == 403

    async def test_no_raw_credentials_in_channel_config(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """bot_token value must never appear in response — only *_configured: bool."""
        svc = _make_mock_service()

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.get(f"{BASE}/channels")

        assert resp.status_code == 200
        _assert_no_raw_credentials(resp.json())


# ---------------------------------------------------------------------------
# TestGetCRMConfig
# ---------------------------------------------------------------------------


class TestGetCRMConfig:
    """GET /api/v1/integrations/crm — HubSpot config (Admin only)."""

    async def test_admin_receives_200_with_crm_config_fields(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Admin receives 200 with all CRMIntegrationConfig fields present."""
        svc = _make_mock_service()

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.get(f"{BASE}/crm")

        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token_configured"] is True
        assert body["auto_create_contacts"] is True
        assert body["default_lead_status"] == "NEW"
        assert body["rate_limit_per_10s"] == 9
        assert body["api_timeout_seconds"] == 30

    async def test_reviewer_receives_403(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer is not authorized — 403."""
        resp = await reviewer_client.get(f"{BASE}/crm")
        assert resp.status_code == 403

    async def test_no_raw_credentials_in_crm_config(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """HubSpot access token value must never appear in response.

        Only access_token_configured: bool is permitted.
        """
        svc = _make_mock_service()

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.get(f"{BASE}/crm")

        assert resp.status_code == 200
        _assert_no_raw_credentials(resp.json())

    async def test_access_token_configured_false_when_unconfigured(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """access_token_configured=False when no HubSpot token is set."""
        cfg = _crm_config()
        cfg["access_token_configured"] = False
        svc = _make_mock_service(crm_cfg=cfg)

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.get(f"{BASE}/crm")

        assert resp.status_code == 200
        assert resp.json()["access_token_configured"] is False


# ---------------------------------------------------------------------------
# TestGetLLMConfig
# ---------------------------------------------------------------------------


class TestGetLLMConfig:
    """GET /api/v1/integrations/llm — LLM config (Admin only)."""

    async def test_admin_receives_200_with_llm_config_fields(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Admin receives 200 with all LLMIntegrationConfig fields present."""
        svc = _make_mock_service()

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.get(f"{BASE}/llm")

        assert resp.status_code == 200
        body = resp.json()
        assert body["openai_api_key_configured"] is True
        assert body["anthropic_api_key_configured"] is False
        assert body["classify_model"] == "gpt-4o-mini"
        assert body["draft_model"] == "gpt-4o"
        assert body["temperature_classify"] == 0.1
        assert body["temperature_draft"] == 0.7
        assert body["fallback_model"] == "gpt-3.5-turbo"
        assert body["timeout_seconds"] == 30
        assert body["base_url"] == "https://api.openai.com/v1"

    async def test_reviewer_receives_403(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer is not authorized — 403."""
        resp = await reviewer_client.get(f"{BASE}/llm")
        assert resp.status_code == 403

    async def test_no_raw_credentials_in_llm_config(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """openai_api_key and anthropic_api_key values must never appear.

        Only *_configured: bool fields are permitted in the response.
        """
        svc = _make_mock_service()

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.get(f"{BASE}/llm")

        assert resp.status_code == 200
        _assert_no_raw_credentials(resp.json())

    async def test_both_api_keys_unconfigured(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """When neither LLM key is set, both *_configured booleans are False."""
        cfg = _llm_config()
        cfg["openai_api_key_configured"] = False
        cfg["anthropic_api_key_configured"] = False
        svc = _make_mock_service(llm_cfg=cfg)

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.get(f"{BASE}/llm")

        assert resp.status_code == 200
        body = resp.json()
        assert body["openai_api_key_configured"] is False
        assert body["anthropic_api_key_configured"] is False


# ---------------------------------------------------------------------------
# TestTestEmailConnection
# ---------------------------------------------------------------------------


class TestTestEmailConnection:
    """POST /api/v1/integrations/email/test — Gmail connection probe (Admin only)."""

    async def test_success_returns_200_with_success_true(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Successful Gmail probe returns 200, success=True, latency_ms present."""
        svc = _make_mock_service(email_test=_connection_success("email"))

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.post(f"{BASE}/email/test")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["latency_ms"] == 42
        assert body["error_detail"] is None
        assert body["adapter_type"] == "email"

    async def test_failure_returns_200_with_success_false(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Failed Gmail probe returns 200 (never 5xx) — success=False, error_detail present."""
        svc = _make_mock_service(email_test=_connection_failure("email", "OAuth token expired"))

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.post(f"{BASE}/email/test")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["error_detail"] == "OAuth token expired"
        assert body["adapter_type"] == "email"

    async def test_reviewer_receives_403(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer is not authorized — 403."""
        resp = await reviewer_client.post(f"{BASE}/email/test")
        assert resp.status_code == 403

    async def test_service_test_email_connection_called(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """IntegrationService.test_email_connection is called exactly once."""
        svc = _make_mock_service()

        with patch("src.api.routers.integrations._integration_service", svc):
            await admin_client.post(f"{BASE}/email/test")

        svc.test_email_connection.assert_called_once()


# ---------------------------------------------------------------------------
# TestTestChannelConnection
# ---------------------------------------------------------------------------


class TestTestChannelConnection:
    """POST /api/v1/integrations/channels/test — Slack connection probe (Admin only)."""

    async def test_success_returns_200_with_success_true(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Successful Slack probe returns 200, success=True."""
        svc = _make_mock_service(channel_test=_connection_success("channels"))

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.post(f"{BASE}/channels/test")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["latency_ms"] == 42
        assert body["adapter_type"] == "channels"

    async def test_failure_returns_200_with_success_false(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Failed Slack probe returns 200 (never 5xx) — success=False, error_detail present."""
        svc = _make_mock_service(channel_test=_connection_failure("channels", "invalid_auth"))

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.post(f"{BASE}/channels/test")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["error_detail"] == "invalid_auth"

    async def test_reviewer_receives_403(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer is not authorized — 403."""
        resp = await reviewer_client.post(f"{BASE}/channels/test")
        assert resp.status_code == 403

    async def test_service_test_channel_connection_called(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """IntegrationService.test_channel_connection is called exactly once."""
        svc = _make_mock_service()

        with patch("src.api.routers.integrations._integration_service", svc):
            await admin_client.post(f"{BASE}/channels/test")

        svc.test_channel_connection.assert_called_once()


# ---------------------------------------------------------------------------
# TestTestCRMConnection
# ---------------------------------------------------------------------------


class TestTestCRMConnection:
    """POST /api/v1/integrations/crm/test — HubSpot connection probe (Admin only)."""

    async def test_success_returns_200_with_success_true(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Successful HubSpot probe returns 200, success=True."""
        svc = _make_mock_service(crm_test=_connection_success("crm"))

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.post(f"{BASE}/crm/test")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["latency_ms"] == 42
        assert body["adapter_type"] == "crm"

    async def test_failure_returns_200_with_success_false(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Failed HubSpot probe returns 200 — success=False, error_detail present."""
        svc = _make_mock_service(crm_test=_connection_failure("crm", "401 Unauthorized"))

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.post(f"{BASE}/crm/test")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["error_detail"] == "401 Unauthorized"

    async def test_reviewer_receives_403(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer is not authorized — 403."""
        resp = await reviewer_client.post(f"{BASE}/crm/test")
        assert resp.status_code == 403

    async def test_service_test_crm_connection_called(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """IntegrationService.test_crm_connection is called exactly once."""
        svc = _make_mock_service()

        with patch("src.api.routers.integrations._integration_service", svc):
            await admin_client.post(f"{BASE}/crm/test")

        svc.test_crm_connection.assert_called_once()


# ---------------------------------------------------------------------------
# TestTestLLMConnection
# ---------------------------------------------------------------------------


class TestTestLLMConnection:
    """POST /api/v1/integrations/llm/test — LLM connection probe (Admin only)."""

    async def test_success_returns_200_with_success_true(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Successful LLM probe returns 200, success=True."""
        svc = _make_mock_service(llm_test=_connection_success("llm"))

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.post(f"{BASE}/llm/test")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["latency_ms"] == 42
        assert body["adapter_type"] == "llm"

    async def test_failure_returns_200_with_success_false(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Failed LLM probe returns 200 — success=False, error_detail present."""
        svc = _make_mock_service(
            llm_test=_connection_failure("llm", "RateLimitError: quota exceeded")
        )

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.post(f"{BASE}/llm/test")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["error_detail"] == "RateLimitError: quota exceeded"

    async def test_reviewer_receives_403(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer is not authorized — 403."""
        resp = await reviewer_client.post(f"{BASE}/llm/test")
        assert resp.status_code == 403

    async def test_service_test_llm_connection_called(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """IntegrationService.test_llm_connection is called exactly once."""
        svc = _make_mock_service()

        with patch("src.api.routers.integrations._integration_service", svc):
            await admin_client.post(f"{BASE}/llm/test")

        svc.test_llm_connection.assert_called_once()


# ---------------------------------------------------------------------------
# TestAuthGuards
# ---------------------------------------------------------------------------


class TestAuthGuards:
    """All 8 endpoints require authentication and Admin role."""

    async def test_unauthenticated_get_email_returns_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """Requests without auth token return 401."""
        resp = await unauthenticated_client.get(f"{BASE}/email")
        assert resp.status_code == 401

    async def test_unauthenticated_post_email_test_returns_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """POST /email/test without auth token returns 401."""
        resp = await unauthenticated_client.post(f"{BASE}/email/test")
        assert resp.status_code == 401

    async def test_unauthenticated_get_channels_returns_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """GET /channels without auth token returns 401."""
        resp = await unauthenticated_client.get(f"{BASE}/channels")
        assert resp.status_code == 401

    async def test_unauthenticated_post_channels_test_returns_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """POST /channels/test without auth token returns 401."""
        resp = await unauthenticated_client.post(f"{BASE}/channels/test")
        assert resp.status_code == 401

    async def test_unauthenticated_get_crm_returns_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """GET /crm without auth token returns 401."""
        resp = await unauthenticated_client.get(f"{BASE}/crm")
        assert resp.status_code == 401

    async def test_unauthenticated_post_crm_test_returns_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """POST /crm/test without auth token returns 401."""
        resp = await unauthenticated_client.post(f"{BASE}/crm/test")
        assert resp.status_code == 401

    async def test_unauthenticated_get_llm_returns_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """GET /llm without auth token returns 401."""
        resp = await unauthenticated_client.get(f"{BASE}/llm")
        assert resp.status_code == 401

    async def test_unauthenticated_post_llm_test_returns_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """POST /llm/test without auth token returns 401."""
        resp = await unauthenticated_client.post(f"{BASE}/llm/test")
        assert resp.status_code == 401

    async def test_reviewer_cannot_access_any_integration_endpoint(
        self,
        reviewer_client: AsyncClient,
    ) -> None:
        """Reviewer role is denied on all 8 integration endpoints — all return 403."""
        endpoints = [
            ("GET", f"{BASE}/email"),
            ("POST", f"{BASE}/email/test"),
            ("GET", f"{BASE}/channels"),
            ("POST", f"{BASE}/channels/test"),
            ("GET", f"{BASE}/crm"),
            ("POST", f"{BASE}/crm/test"),
            ("GET", f"{BASE}/llm"),
            ("POST", f"{BASE}/llm/test"),
        ]
        for method, path in endpoints:
            if method == "GET":
                resp = await reviewer_client.get(path)
            else:
                resp = await reviewer_client.post(path)
            assert resp.status_code == 403, (
                f"Expected 403 for reviewer on {method} {path}, got {resp.status_code}"
            )


# ---------------------------------------------------------------------------
# TestConnectionTestResultShape
# ---------------------------------------------------------------------------


class TestConnectionTestResultShape:
    """ConnectionTestResult schema — field presence and type contracts."""

    async def test_all_connection_result_fields_present_on_success(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """Success result contains success, latency_ms, error_detail, adapter_type."""
        svc = _make_mock_service(email_test=_connection_success("email"))

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.post(f"{BASE}/email/test")

        body = resp.json()
        assert "success" in body
        assert "latency_ms" in body
        assert "error_detail" in body
        assert "adapter_type" in body

    async def test_error_detail_none_on_success(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """error_detail is None (not absent) when the connection test succeeds."""
        svc = _make_mock_service(llm_test=_connection_success("llm"))

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.post(f"{BASE}/llm/test")

        body = resp.json()
        assert body["success"] is True
        assert body["error_detail"] is None

    async def test_latency_ms_is_integer_on_success(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """latency_ms is an integer, not a float or string, when present."""
        svc = _make_mock_service(crm_test=_connection_success("crm"))

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.post(f"{BASE}/crm/test")

        body = resp.json()
        assert isinstance(body["latency_ms"], int)

    async def test_success_false_with_none_latency_ms(
        self,
        admin_client: AsyncClient,
    ) -> None:
        """latency_ms can be None even on failure (e.g. instant connection refused)."""
        failure_result: dict[str, object] = {
            "success": False,
            "latency_ms": None,
            "error_detail": "connection refused",
            "adapter_type": "channels",
        }
        svc = _make_mock_service(channel_test=failure_result)

        with patch("src.api.routers.integrations._integration_service", svc):
            resp = await admin_client.post(f"{BASE}/channels/test")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["latency_ms"] is None
        assert body["error_detail"] == "connection refused"
