"""Tests for LiteLLMAdapter with mocked litellm.acompletion.

Uses ``unittest.mock`` to replace ``litellm.acompletion``. No real API calls.
Runs in the default ``pytest tests/ -q`` suite.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.llm.exceptions import (
    LLMConnectionError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from src.adapters.llm.litellm_adapter import LiteLLMAdapter
from src.adapters.llm.schemas import (
    ClassificationResult,
    ClassifyOptions,
    ConnectionTestResult,
    DraftOptions,
    DraftText,
    LLMConfig,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> LLMConfig:
    return LLMConfig(
        classify_model="gpt-4o-mini",
        draft_model="gpt-4o",
        fallback_model="gpt-3.5-turbo",
        api_key="sk-test",
        timeout_seconds=30,
    )


@pytest.fixture
def adapter(config: LLMConfig) -> LiteLLMAdapter:
    return LiteLLMAdapter(config)


@pytest.fixture
def classify_options() -> ClassifyOptions:
    return ClassifyOptions(
        allowed_actions=["reply", "forward", "inform"],
        allowed_types=["support", "sales", "notification"],
    )


@pytest.fixture
def draft_options() -> DraftOptions:
    return DraftOptions()


def _mock_response(content: str) -> MagicMock:
    """Build a mock litellm ModelResponse with the given content."""
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    return response


# ---------------------------------------------------------------------------
# classify — success
# ---------------------------------------------------------------------------


class TestClassifySuccess:
    """Successful classification with valid LLM output."""

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_valid_json_response(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        mock_completion.return_value = _mock_response('{"action": "reply", "type": "support"}')
        result = await adapter.classify("test email", "classify this", classify_options)

        assert isinstance(result, ClassificationResult)
        assert result.action == "reply"
        assert result.type == "support"
        assert result.confidence == "high"
        assert result.fallback_applied is False

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_uses_correct_model(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        mock_completion.return_value = _mock_response('{"action": "reply", "type": "support"}')
        await adapter.classify("test", "system", classify_options)

        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_model_override(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
    ) -> None:
        mock_completion.return_value = _mock_response('{"action": "reply", "type": "support"}')
        options = ClassifyOptions(
            allowed_actions=["reply"],
            allowed_types=["support"],
            model="claude-3-haiku",
        )
        await adapter.classify("test", "system", options)

        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs["model"] == "claude-3-haiku"

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_raw_llm_output_preserved(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        raw = '{"action": "inform", "type": "notification"}'
        mock_completion.return_value = _mock_response(raw)
        result = await adapter.classify("test", "system", classify_options)

        assert result.raw_llm_output == raw


# ---------------------------------------------------------------------------
# classify — fallback
# ---------------------------------------------------------------------------


class TestClassifyFallback:
    """classify() applies fallback when parser returns None."""

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_unparseable_output_triggers_fallback(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        mock_completion.return_value = _mock_response("I cannot classify this email")
        result = await adapter.classify("test", "system", classify_options)

        assert result.fallback_applied is True
        assert result.action == "inform"
        assert result.type == "notification"
        assert result.confidence == "low"
        assert result.raw_llm_output == "I cannot classify this email"

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_empty_response_triggers_fallback(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        mock_completion.return_value = _mock_response("")
        result = await adapter.classify("test", "system", classify_options)

        assert result.fallback_applied is True

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_none_content_triggers_fallback(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content=None))]
        mock_completion.return_value = response
        result = await adapter.classify("test", "system", classify_options)

        assert result.fallback_applied is True

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_action_not_in_allowed_triggers_fallback(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        # Parser returns None when action not in allowed_actions
        mock_completion.return_value = _mock_response('{"action": "delete", "type": "support"}')
        result = await adapter.classify("test", "system", classify_options)

        assert result.fallback_applied is True
        assert result.confidence == "low"

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_fallback_raw_output_preserved(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        raw = "sorry I cannot parse this"
        mock_completion.return_value = _mock_response(raw)
        result = await adapter.classify("test", "system", classify_options)

        assert result.fallback_applied is True
        assert result.raw_llm_output == raw


# ---------------------------------------------------------------------------
# classify — precondition errors
# ---------------------------------------------------------------------------


class TestClassifyPreconditions:
    """classify() raises ValueError for invalid preconditions."""

    async def test_empty_prompt_raises(
        self,
        adapter: LiteLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        with pytest.raises(ValueError, match="prompt must not be empty"):
            await adapter.classify("", "system", classify_options)

    async def test_empty_system_prompt_raises(
        self,
        adapter: LiteLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        with pytest.raises(ValueError, match="system_prompt must not be empty"):
            await adapter.classify("test", "", classify_options)

    async def test_empty_allowed_actions_raises(
        self,
        adapter: LiteLLMAdapter,
    ) -> None:
        options = ClassifyOptions(
            allowed_actions=["x"],
            allowed_types=["support"],
        )
        options.allowed_actions = []  # bypass Pydantic validation
        with pytest.raises(ValueError, match="allowed_actions must not be empty"):
            await adapter.classify("test", "system", options)

    async def test_empty_allowed_types_raises(
        self,
        adapter: LiteLLMAdapter,
    ) -> None:
        options = ClassifyOptions(
            allowed_actions=["reply"],
            allowed_types=["x"],
        )
        options.allowed_types = []  # bypass Pydantic validation
        with pytest.raises(ValueError, match="allowed_types must not be empty"):
            await adapter.classify("test", "system", options)

    async def test_no_api_call_on_precondition_failure(
        self,
        adapter: LiteLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        """ValueError is raised before any external call is made."""
        with patch(
            "src.adapters.llm.litellm_adapter.litellm.acompletion",
            new_callable=AsyncMock,
        ) as mock_completion:
            with pytest.raises(ValueError):
                await adapter.classify("", "system", classify_options)
            mock_completion.assert_not_called()


# ---------------------------------------------------------------------------
# classify — exception mapping
# ---------------------------------------------------------------------------


class TestClassifyExceptionMapping:
    """classify() maps litellm exceptions to domain exceptions."""

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_rate_limit_error(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        import litellm.exceptions as litellm_exc

        mock_completion.side_effect = litellm_exc.RateLimitError(
            message="rate limited",
            llm_provider="openai",
            model="gpt-4o-mini",
        )
        with pytest.raises(LLMRateLimitError):
            await adapter.classify("test", "system", classify_options)

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_timeout_error(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        import litellm.exceptions as litellm_exc

        mock_completion.side_effect = litellm_exc.Timeout(
            message="timeout",
            model="gpt-4o-mini",
            llm_provider="openai",
        )
        with pytest.raises(LLMTimeoutError):
            await adapter.classify("test", "system", classify_options)

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_connection_error(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        import litellm.exceptions as litellm_exc

        mock_completion.side_effect = litellm_exc.APIConnectionError(
            message="connection failed",
            llm_provider="openai",
            model="gpt-4o-mini",
        )
        with pytest.raises(LLMConnectionError):
            await adapter.classify("test", "system", classify_options)

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_rate_limit_wraps_original_error(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        import litellm.exceptions as litellm_exc

        original = litellm_exc.RateLimitError(
            message="rate limited",
            llm_provider="openai",
            model="gpt-4o-mini",
        )
        mock_completion.side_effect = original
        with pytest.raises(LLMRateLimitError) as exc_info:
            await adapter.classify("test", "system", classify_options)
        assert exc_info.value.original_error is original


# ---------------------------------------------------------------------------
# generate_draft — success
# ---------------------------------------------------------------------------


class TestGenerateDraftSuccess:
    """Successful draft generation."""

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_valid_draft(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        draft_options: DraftOptions,
    ) -> None:
        mock_completion.return_value = _mock_response("Thank you for your inquiry.")
        result = await adapter.generate_draft("email content", "be polite", draft_options)

        assert isinstance(result, DraftText)
        assert result.content == "Thank you for your inquiry."
        assert result.model_used == "gpt-4o"
        assert result.fallback_applied is False

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_uses_draft_model(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        draft_options: DraftOptions,
    ) -> None:
        mock_completion.return_value = _mock_response("Draft content")
        await adapter.generate_draft("test", "system", draft_options)

        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o"

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_model_override(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
    ) -> None:
        mock_completion.return_value = _mock_response("Draft content")
        options = DraftOptions(model="claude-3-opus")
        await adapter.generate_draft("test", "system", options)

        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs["model"] == "claude-3-opus"

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_empty_llm_content_returns_empty_string(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        draft_options: DraftOptions,
    ) -> None:
        """None content from LLM is coerced to empty string — no fallback for drafts."""
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content=None))]
        mock_completion.return_value = response
        result = await adapter.generate_draft("test", "system", draft_options)

        assert result.content == ""
        assert result.fallback_applied is False


# ---------------------------------------------------------------------------
# generate_draft — precondition errors
# ---------------------------------------------------------------------------


class TestGenerateDraftPreconditions:
    """generate_draft() raises ValueError for invalid preconditions."""

    async def test_empty_prompt_raises(
        self,
        adapter: LiteLLMAdapter,
        draft_options: DraftOptions,
    ) -> None:
        with pytest.raises(ValueError, match="prompt must not be empty"):
            await adapter.generate_draft("", "system", draft_options)

    async def test_empty_system_prompt_raises(
        self,
        adapter: LiteLLMAdapter,
        draft_options: DraftOptions,
    ) -> None:
        with pytest.raises(ValueError, match="system_prompt must not be empty"):
            await adapter.generate_draft("test", "", draft_options)

    async def test_no_api_call_on_precondition_failure(
        self,
        adapter: LiteLLMAdapter,
        draft_options: DraftOptions,
    ) -> None:
        """ValueError is raised before any external call is made."""
        with patch(
            "src.adapters.llm.litellm_adapter.litellm.acompletion",
            new_callable=AsyncMock,
        ) as mock_completion:
            with pytest.raises(ValueError):
                await adapter.generate_draft("", "system", draft_options)
            mock_completion.assert_not_called()


# ---------------------------------------------------------------------------
# generate_draft — exception mapping
# ---------------------------------------------------------------------------


class TestGenerateDraftExceptionMapping:
    """generate_draft() maps litellm exceptions to domain exceptions."""

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_rate_limit_propagates(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        draft_options: DraftOptions,
    ) -> None:
        import litellm.exceptions as litellm_exc

        mock_completion.side_effect = litellm_exc.RateLimitError(
            message="rate limited",
            llm_provider="openai",
            model="gpt-4o",
        )
        with pytest.raises(LLMRateLimitError):
            await adapter.generate_draft("test", "system", draft_options)

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_timeout_propagates(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        draft_options: DraftOptions,
    ) -> None:
        import litellm.exceptions as litellm_exc

        mock_completion.side_effect = litellm_exc.Timeout(
            message="timeout",
            model="gpt-4o",
            llm_provider="openai",
        )
        with pytest.raises(LLMTimeoutError):
            await adapter.generate_draft("test", "system", draft_options)

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_connection_error_propagates(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        draft_options: DraftOptions,
    ) -> None:
        import litellm.exceptions as litellm_exc

        mock_completion.side_effect = litellm_exc.APIConnectionError(
            message="connection failed",
            llm_provider="openai",
            model="gpt-4o",
        )
        with pytest.raises(LLMConnectionError):
            await adapter.generate_draft("test", "system", draft_options)

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_no_fallback_on_error(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
        draft_options: DraftOptions,
    ) -> None:
        """generate_draft() has no fallback — errors always propagate."""
        import litellm.exceptions as litellm_exc

        mock_completion.side_effect = litellm_exc.Timeout(
            message="timeout",
            model="gpt-4o",
            llm_provider="openai",
        )
        with pytest.raises(LLMTimeoutError):
            await adapter.generate_draft("test", "system", draft_options)


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------


class TestTestConnection:
    """test_connection() never raises — always returns ConnectionTestResult."""

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_success(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
    ) -> None:
        mock_completion.return_value = _mock_response("pong")
        result = await adapter.test_connection()

        assert isinstance(result, ConnectionTestResult)
        assert result.success is True
        assert result.model_used == "gpt-4o-mini"
        assert result.latency_ms >= 0
        assert result.error_detail is None

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_failure_returns_result(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
    ) -> None:
        mock_completion.side_effect = ConnectionError("refused")
        result = await adapter.test_connection()

        assert result.success is False
        assert result.error_detail is not None
        assert "refused" in result.error_detail

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_measures_latency(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
    ) -> None:
        mock_completion.return_value = _mock_response("pong")
        result = await adapter.test_connection()

        assert result.latency_ms >= 0

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_uses_classify_model_for_ping(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
    ) -> None:
        mock_completion.return_value = _mock_response("pong")
        result = await adapter.test_connection()

        assert result.model_used == "gpt-4o-mini"
        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_rate_limit_error_returns_failure(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
    ) -> None:
        """Even LLM-specific errors are silenced by test_connection()."""
        import litellm.exceptions as litellm_exc

        mock_completion.side_effect = litellm_exc.RateLimitError(
            message="rate limited",
            llm_provider="openai",
            model="gpt-4o-mini",
        )
        result = await adapter.test_connection()

        assert result.success is False
        assert result.error_detail is not None

    @patch("src.adapters.llm.litellm_adapter.litellm.acompletion", new_callable=AsyncMock)
    async def test_failure_latency_measured(
        self,
        mock_completion: AsyncMock,
        adapter: LiteLLMAdapter,
    ) -> None:
        """Latency is measured even on failure."""
        mock_completion.side_effect = ConnectionError("refused")
        result = await adapter.test_connection()

        assert result.latency_ms >= 0
        assert result.success is False
