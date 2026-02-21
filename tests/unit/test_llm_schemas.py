"""Unit tests for LLM adapter boundary schemas.

Validates Pydantic models for ClassificationResult, DraftText,
ClassifyOptions, DraftOptions, LLMConfig, and ConnectionTestResult.
No external dependencies — pure schema validation.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.adapters.llm.schemas import (
    ClassificationResult,
    ClassifyOptions,
    ConnectionTestResult,
    DraftOptions,
    DraftText,
    LLMConfig,
)


# ---------------------------------------------------------------------------
# ClassificationResult
# ---------------------------------------------------------------------------


class TestClassificationResult:
    """Validates ClassificationResult construction and constraints."""

    def test_valid_high_confidence(self) -> None:
        result = ClassificationResult(
            action="reply",
            type="support",
            confidence="high",
            raw_llm_output='{"action":"reply","type":"support"}',
        )
        assert result.action == "reply"
        assert result.type == "support"
        assert result.confidence == "high"
        assert result.fallback_applied is False

    def test_valid_low_confidence_with_fallback(self) -> None:
        result = ClassificationResult(
            action="inform",
            type="notification",
            confidence="low",
            raw_llm_output="unparseable garbage",
            fallback_applied=True,
        )
        assert result.fallback_applied is True
        assert result.confidence == "low"

    def test_invalid_confidence_rejected(self) -> None:
        with pytest.raises(ValidationError, match="confidence"):
            ClassificationResult(
                action="reply",
                type="support",
                confidence="medium",  # type: ignore[arg-type]
                raw_llm_output="test",
            )

    def test_extra_fields_ignored(self) -> None:
        """ConfigDict(extra='ignore') drops unexpected fields."""
        result = ClassificationResult(
            action="reply",
            type="support",
            confidence="high",
            raw_llm_output="test",
            explanation="this should be ignored",  # type: ignore[call-arg]
        )
        assert not hasattr(result, "explanation")

    def test_missing_required_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClassificationResult(
                action="reply",
                confidence="high",
                raw_llm_output="test",
                # missing type
            )  # type: ignore[call-arg]

    def test_raw_llm_output_preserved(self) -> None:
        raw = '{"action":"reply","type":"support","extra":"data"}'
        result = ClassificationResult(
            action="reply",
            type="support",
            confidence="high",
            raw_llm_output=raw,
        )
        assert result.raw_llm_output == raw


# ---------------------------------------------------------------------------
# DraftText
# ---------------------------------------------------------------------------


class TestDraftText:
    """Validates DraftText construction."""

    def test_valid_construction(self) -> None:
        draft = DraftText(
            content="Thank you for your email.",
            model_used="gpt-4o",
        )
        assert draft.content == "Thank you for your email."
        assert draft.model_used == "gpt-4o"
        assert draft.fallback_applied is False

    def test_with_fallback(self) -> None:
        draft = DraftText(
            content="Fallback content",
            model_used="gpt-3.5-turbo",
            fallback_applied=True,
        )
        assert draft.fallback_applied is True

    def test_missing_content_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DraftText(model_used="gpt-4o")  # type: ignore[call-arg]

    def test_missing_model_used_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DraftText(content="Hello")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ClassifyOptions
# ---------------------------------------------------------------------------


class TestClassifyOptions:
    """Validates ClassifyOptions construction and constraints."""

    def test_valid_with_defaults(self) -> None:
        opts = ClassifyOptions(
            allowed_actions=["reply", "forward"],
            allowed_types=["support", "sales"],
        )
        assert opts.temperature == 0.1
        assert opts.max_tokens == 500
        assert opts.model is None

    def test_custom_values(self) -> None:
        opts = ClassifyOptions(
            allowed_actions=["reply"],
            allowed_types=["support"],
            temperature=0.5,
            max_tokens=1000,
            model="gpt-4o",
        )
        assert opts.temperature == 0.5
        assert opts.max_tokens == 1000
        assert opts.model == "gpt-4o"

    def test_empty_allowed_actions_rejected(self) -> None:
        with pytest.raises(ValidationError, match="allowed_actions"):
            ClassifyOptions(
                allowed_actions=[],
                allowed_types=["support"],
            )

    def test_empty_allowed_types_rejected(self) -> None:
        with pytest.raises(ValidationError, match="allowed_types"):
            ClassifyOptions(
                allowed_actions=["reply"],
                allowed_types=[],
            )

    def test_temperature_too_high_rejected(self) -> None:
        with pytest.raises(ValidationError, match="temperature"):
            ClassifyOptions(
                allowed_actions=["reply"],
                allowed_types=["support"],
                temperature=1.5,
            )

    def test_temperature_negative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="temperature"):
            ClassifyOptions(
                allowed_actions=["reply"],
                allowed_types=["support"],
                temperature=-0.1,
            )

    def test_max_tokens_zero_rejected(self) -> None:
        with pytest.raises(ValidationError, match="max_tokens"):
            ClassifyOptions(
                allowed_actions=["reply"],
                allowed_types=["support"],
                max_tokens=0,
            )


# ---------------------------------------------------------------------------
# DraftOptions
# ---------------------------------------------------------------------------


class TestDraftOptions:
    """Validates DraftOptions construction and constraints."""

    def test_valid_with_defaults(self) -> None:
        opts = DraftOptions()
        assert opts.temperature == 0.7
        assert opts.max_tokens == 2000
        assert opts.model is None

    def test_custom_values(self) -> None:
        opts = DraftOptions(temperature=0.9, max_tokens=3000, model="gpt-4o")
        assert opts.temperature == 0.9
        assert opts.max_tokens == 3000

    def test_temperature_boundary_zero(self) -> None:
        opts = DraftOptions(temperature=0.0)
        assert opts.temperature == 0.0

    def test_temperature_boundary_one(self) -> None:
        opts = DraftOptions(temperature=1.0)
        assert opts.temperature == 1.0


# ---------------------------------------------------------------------------
# LLMConfig
# ---------------------------------------------------------------------------


class TestLLMConfig:
    """Validates LLMConfig construction."""

    def test_valid_full_construction(self) -> None:
        config = LLMConfig(
            classify_model="gpt-4o-mini",
            draft_model="gpt-4o",
            fallback_model="gpt-3.5-turbo",
            api_key="sk-test",
            base_url="http://localhost:11434",
            timeout_seconds=60,
        )
        assert config.classify_model == "gpt-4o-mini"
        assert config.timeout_seconds == 60

    def test_valid_minimal_construction(self) -> None:
        config = LLMConfig(
            classify_model="gpt-4o-mini",
            draft_model="gpt-4o",
            fallback_model="gpt-3.5-turbo",
        )
        assert config.api_key is None
        assert config.base_url is None
        assert config.timeout_seconds == 30

    def test_missing_classify_model_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LLMConfig(
                draft_model="gpt-4o",
                fallback_model="gpt-3.5-turbo",
            )  # type: ignore[call-arg]

    def test_missing_fallback_model_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LLMConfig(
                classify_model="gpt-4o-mini",
                draft_model="gpt-4o",
            )  # type: ignore[call-arg]

    def test_timeout_zero_rejected(self) -> None:
        with pytest.raises(ValidationError, match="timeout_seconds"):
            LLMConfig(
                classify_model="gpt-4o-mini",
                draft_model="gpt-4o",
                fallback_model="gpt-3.5-turbo",
                timeout_seconds=0,
            )


# ---------------------------------------------------------------------------
# ConnectionTestResult
# ---------------------------------------------------------------------------


class TestConnectionTestResult:
    """Validates ConnectionTestResult construction."""

    def test_success_result(self) -> None:
        result = ConnectionTestResult(
            success=True,
            model_used="gpt-4o-mini",
            latency_ms=150,
        )
        assert result.success is True
        assert result.error_detail is None

    def test_failure_result(self) -> None:
        result = ConnectionTestResult(
            success=False,
            model_used="gpt-4o-mini",
            latency_ms=0,
            error_detail="Connection refused",
        )
        assert result.success is False
        assert result.error_detail == "Connection refused"

    def test_missing_model_used_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ConnectionTestResult(
                success=True,
                latency_ms=100,
            )  # type: ignore[call-arg]
