"""Unit tests for LLM allowlist — WARNING-01 security fix.

Validates that:
- Models in the allowlist are permitted.
- Models outside the allowlist raise ValueError before any LLM call.
- An empty llm_allowed_models env var defaults to the three configured model names.
- Comma-separated parsing works correctly.

No external dependencies — litellm.acompletion is mocked at the module level.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.llm.litellm_adapter import LiteLLMAdapter
from src.adapters.llm.schemas import (
    ClassifyOptions,
    DraftOptions,
    LLMConfig,
)
from src.core.config import Settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides: str) -> Settings:
    """Build a minimal Settings object without reading .env.

    Uses snake_case field names (not UPPER_CASE env var names) because
    pydantic-settings constructor expects the field alias, not the env key.
    """
    base: dict[str, str] = {
        "database_url": "postgresql+asyncpg://u:p@host/db",
        "database_url_sync": "postgresql+psycopg2://u:p@host/db",
        "jwt_secret_key": "test-secret",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


def _make_config(allowed_models: frozenset[str] = frozenset()) -> LLMConfig:
    return LLMConfig(
        classify_model="gpt-4o-mini",
        draft_model="gpt-4o",
        fallback_model="gpt-3.5-turbo",
        allowed_models=allowed_models,
    )


_DEFAULT_CLASSIFY_CONTENT = '{"action":"reply","type":"support","confidence":"high"}'


def _mock_litellm_response(content: str = _DEFAULT_CLASSIFY_CONTENT) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# TestAllowedModelsConfig — Settings parsing
# ---------------------------------------------------------------------------


class TestAllowedModelsConfig:
    """Settings.llm_allowed_models_set is populated correctly by model_validator."""

    def test_empty_string_defaults_to_configured_models(self) -> None:
        settings = _make_settings(llm_allowed_models="")

        assert settings.llm_allowed_models_set == {
            settings.llm_model_classify,
            settings.llm_model_draft,
            settings.llm_fallback_model,
        }

    def test_comma_separated_parsing(self) -> None:
        settings = _make_settings(llm_allowed_models="gpt-4o,gpt-4o-mini,claude-3-haiku")

        assert settings.llm_allowed_models_set == frozenset(
            {"gpt-4o", "gpt-4o-mini", "claude-3-haiku"}
        )

    def test_comma_separated_strips_whitespace(self) -> None:
        settings = _make_settings(llm_allowed_models=" gpt-4o , gpt-4o-mini ")

        assert "gpt-4o" in settings.llm_allowed_models_set
        assert "gpt-4o-mini" in settings.llm_allowed_models_set

    def test_single_model_parsed_as_singleton_set(self) -> None:
        settings = _make_settings(llm_allowed_models="gpt-4o")

        assert settings.llm_allowed_models_set == frozenset({"gpt-4o"})

    def test_result_is_frozenset(self) -> None:
        settings = _make_settings(llm_allowed_models="gpt-4o")

        assert isinstance(settings.llm_allowed_models_set, frozenset)


# ---------------------------------------------------------------------------
# TestLLMConfigAllowedModels — LLMConfig schema field
# ---------------------------------------------------------------------------


class TestLLMConfigAllowedModels:
    """LLMConfig.allowed_models field defaults to empty frozenset."""

    def test_default_is_empty_frozenset(self) -> None:
        config = LLMConfig(
            classify_model="gpt-4o-mini",
            draft_model="gpt-4o",
            fallback_model="gpt-3.5-turbo",
        )
        assert config.allowed_models == frozenset()
        assert isinstance(config.allowed_models, frozenset)

    def test_explicit_allowed_models(self) -> None:
        config = LLMConfig(
            classify_model="gpt-4o-mini",
            draft_model="gpt-4o",
            fallback_model="gpt-3.5-turbo",
            allowed_models=frozenset({"gpt-4o-mini", "gpt-4o"}),
        )
        assert "gpt-4o-mini" in config.allowed_models
        assert "gpt-4o" in config.allowed_models


# ---------------------------------------------------------------------------
# TestClassifyAllowlistEnforcement — classify() blocks disallowed models
# ---------------------------------------------------------------------------


class TestClassifyAllowlistEnforcement:
    """classify() raises ValueError before calling litellm when model is blocked."""

    @pytest.fixture()
    def adapter_with_allowlist(self) -> LiteLLMAdapter:
        config = _make_config(allowed_models=frozenset({"gpt-4o-mini", "gpt-4o"}))
        return LiteLLMAdapter(config)

    async def test_allowed_model_calls_litellm(
        self, adapter_with_allowlist: LiteLLMAdapter
    ) -> None:
        mock_response = _mock_litellm_response()
        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await adapter_with_allowlist.classify(
                prompt="Classify this email",
                system_prompt="You are a classifier.",
                options=ClassifyOptions(
                    allowed_actions=["reply"],
                    allowed_types=["support"],
                    model="gpt-4o-mini",
                ),
            )
        assert result.action == "reply"

    async def test_disallowed_model_raises_value_error(
        self, adapter_with_allowlist: LiteLLMAdapter
    ) -> None:
        with pytest.raises(ValueError, match="not in the allowed models list"):
            await adapter_with_allowlist.classify(
                prompt="Classify this email",
                system_prompt="You are a classifier.",
                options=ClassifyOptions(
                    allowed_actions=["reply"],
                    allowed_types=["support"],
                    model="gpt-3.5-turbo",  # not in allowlist
                ),
            )

    async def test_disallowed_model_never_calls_litellm(
        self, adapter_with_allowlist: LiteLLMAdapter
    ) -> None:
        with (
            patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion,
            pytest.raises(ValueError),
        ):
            await adapter_with_allowlist.classify(
                prompt="test",
                system_prompt="test",
                options=ClassifyOptions(
                    allowed_actions=["reply"],
                    allowed_types=["support"],
                    model="evil-model",
                ),
            )
        mock_completion.assert_not_called()

    async def test_empty_allowlist_skips_check(self) -> None:
        """Empty frozenset means no restriction — all models pass."""
        config = _make_config(allowed_models=frozenset())
        adapter = LiteLLMAdapter(config)
        mock_response = _mock_litellm_response()

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await adapter.classify(
                prompt="test",
                system_prompt="test",
                options=ClassifyOptions(
                    allowed_actions=["reply"],
                    allowed_types=["support"],
                    model="any-model-name",
                ),
            )
        # Reached here without ValueError — allowed
        assert result is not None


# ---------------------------------------------------------------------------
# TestGenerateDraftAllowlistEnforcement — generate_draft() blocks disallowed models
# ---------------------------------------------------------------------------


class TestGenerateDraftAllowlistEnforcement:
    """generate_draft() raises ValueError before calling litellm when model is blocked."""

    @pytest.fixture()
    def adapter_with_allowlist(self) -> LiteLLMAdapter:
        config = _make_config(allowed_models=frozenset({"gpt-4o"}))
        return LiteLLMAdapter(config)

    async def test_allowed_model_calls_litellm(
        self, adapter_with_allowlist: LiteLLMAdapter
    ) -> None:
        mock_response = _mock_litellm_response(content="Dear customer,")
        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await adapter_with_allowlist.generate_draft(
                prompt="Write a reply",
                system_prompt="You are a helpful assistant.",
                options=DraftOptions(model="gpt-4o"),
            )
        assert result.model_used == "gpt-4o"

    async def test_disallowed_model_raises_value_error(
        self, adapter_with_allowlist: LiteLLMAdapter
    ) -> None:
        with pytest.raises(ValueError, match="not in the allowed models list"):
            await adapter_with_allowlist.generate_draft(
                prompt="Write a reply",
                system_prompt="You are a helpful assistant.",
                options=DraftOptions(model="gpt-3.5-turbo"),  # not in allowlist
            )

    async def test_disallowed_model_never_calls_litellm(
        self, adapter_with_allowlist: LiteLLMAdapter
    ) -> None:
        with (
            patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion,
            pytest.raises(ValueError),
        ):
            await adapter_with_allowlist.generate_draft(
                prompt="test",
                system_prompt="test",
                options=DraftOptions(model="unauthorized-model"),
            )
        mock_completion.assert_not_called()
