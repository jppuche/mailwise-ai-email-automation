"""Contract tests for the LLMAdapter ABC.

Uses a ``MockLLMAdapter`` that implements all 3 abstract methods.
Verifies that *any* correct implementation satisfies the contract:
correct return types, expected exceptions for invalid inputs,
``test_connection()`` never raises.
"""

from __future__ import annotations

import pytest

from src.adapters.llm.base import LLMAdapter
from src.adapters.llm.schemas import (
    ClassificationResult,
    ClassifyOptions,
    ConnectionTestResult,
    DraftOptions,
    DraftText,
)

# ---------------------------------------------------------------------------
# MockLLMAdapter — minimal concrete implementation
# ---------------------------------------------------------------------------


class MockLLMAdapter(LLMAdapter):
    """Simplest valid implementation satisfying the ABC contract."""

    async def classify(
        self,
        prompt: str,
        system_prompt: str,
        options: ClassifyOptions,
    ) -> ClassificationResult:
        if not prompt:
            raise ValueError("prompt must not be empty")
        if not system_prompt:
            raise ValueError("system_prompt must not be empty")
        if not options.allowed_actions:
            raise ValueError("allowed_actions must not be empty")
        if not options.allowed_types:
            raise ValueError("allowed_types must not be empty")
        return ClassificationResult(
            action=options.allowed_actions[0],
            type=options.allowed_types[0],
            confidence="high",
            raw_llm_output='{"mock": true}',
            fallback_applied=False,
        )

    async def generate_draft(
        self,
        prompt: str,
        system_prompt: str,
        options: DraftOptions,
    ) -> DraftText:
        if not prompt:
            raise ValueError("prompt must not be empty")
        if not system_prompt:
            raise ValueError("system_prompt must not be empty")
        return DraftText(
            content="Mock draft response",
            model_used="mock-model",
            fallback_applied=False,
        )

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            success=True,
            model_used="mock-model",
            latency_ms=1,
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def adapter() -> MockLLMAdapter:
    return MockLLMAdapter()


@pytest.fixture
def classify_options() -> ClassifyOptions:
    return ClassifyOptions(
        allowed_actions=["reply", "forward"],
        allowed_types=["support", "sales"],
    )


@pytest.fixture
def draft_options() -> DraftOptions:
    return DraftOptions()


# ---------------------------------------------------------------------------
# classify contract
# ---------------------------------------------------------------------------


class TestClassifyContract:
    """Any LLMAdapter.classify() implementation must satisfy these."""

    async def test_returns_classification_result(
        self,
        adapter: MockLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        result = await adapter.classify("test email", "classify", classify_options)
        assert isinstance(result, ClassificationResult)

    async def test_result_has_required_fields(
        self,
        adapter: MockLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        result = await adapter.classify("test email", "classify", classify_options)
        assert isinstance(result.action, str)
        assert isinstance(result.type, str)
        assert result.confidence in ("high", "low")
        assert isinstance(result.raw_llm_output, str)
        assert isinstance(result.fallback_applied, bool)

    async def test_empty_prompt_raises_value_error(
        self,
        adapter: MockLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        with pytest.raises(ValueError, match="prompt"):
            await adapter.classify("", "system", classify_options)

    async def test_empty_system_prompt_raises_value_error(
        self,
        adapter: MockLLMAdapter,
        classify_options: ClassifyOptions,
    ) -> None:
        with pytest.raises(ValueError, match="system_prompt"):
            await adapter.classify("test", "", classify_options)

    async def test_empty_allowed_actions_raises_value_error(
        self,
        adapter: MockLLMAdapter,
    ) -> None:
        options = ClassifyOptions(
            allowed_actions=["x"],
            allowed_types=["support"],
        )
        options.allowed_actions = []
        with pytest.raises(ValueError, match="allowed_actions"):
            await adapter.classify("test", "system", options)

    async def test_empty_allowed_types_raises_value_error(
        self,
        adapter: MockLLMAdapter,
    ) -> None:
        options = ClassifyOptions(
            allowed_actions=["reply"],
            allowed_types=["x"],
        )
        options.allowed_types = []
        with pytest.raises(ValueError, match="allowed_types"):
            await adapter.classify("test", "system", options)


# ---------------------------------------------------------------------------
# generate_draft contract
# ---------------------------------------------------------------------------


class TestGenerateDraftContract:
    """Any LLMAdapter.generate_draft() implementation must satisfy these."""

    async def test_returns_draft_text(
        self,
        adapter: MockLLMAdapter,
        draft_options: DraftOptions,
    ) -> None:
        result = await adapter.generate_draft("email content", "be polite", draft_options)
        assert isinstance(result, DraftText)

    async def test_result_has_required_fields(
        self,
        adapter: MockLLMAdapter,
        draft_options: DraftOptions,
    ) -> None:
        result = await adapter.generate_draft("email", "system", draft_options)
        assert isinstance(result.content, str)
        assert isinstance(result.model_used, str)
        assert isinstance(result.fallback_applied, bool)

    async def test_empty_prompt_raises_value_error(
        self,
        adapter: MockLLMAdapter,
        draft_options: DraftOptions,
    ) -> None:
        with pytest.raises(ValueError, match="prompt"):
            await adapter.generate_draft("", "system", draft_options)

    async def test_empty_system_prompt_raises_value_error(
        self,
        adapter: MockLLMAdapter,
        draft_options: DraftOptions,
    ) -> None:
        with pytest.raises(ValueError, match="system_prompt"):
            await adapter.generate_draft("test", "", draft_options)


# ---------------------------------------------------------------------------
# test_connection contract
# ---------------------------------------------------------------------------


class TestTestConnectionContract:
    """test_connection() must NEVER raise — always returns ConnectionTestResult."""

    async def test_returns_connection_test_result(
        self,
        adapter: MockLLMAdapter,
    ) -> None:
        result = await adapter.test_connection()
        assert isinstance(result, ConnectionTestResult)

    async def test_result_has_required_fields(
        self,
        adapter: MockLLMAdapter,
    ) -> None:
        result = await adapter.test_connection()
        assert isinstance(result.success, bool)
        assert isinstance(result.model_used, str)
        assert isinstance(result.latency_ms, int)


# ---------------------------------------------------------------------------
# ABC enforcement
# ---------------------------------------------------------------------------


class TestABCEnforcement:
    """Cannot instantiate LLMAdapter without implementing all methods."""

    def test_cannot_instantiate_abc(self) -> None:
        with pytest.raises(TypeError, match="abstract method"):
            LLMAdapter()  # type: ignore[abstract]

    def test_partial_implementation_rejected(self) -> None:
        class PartialAdapter(LLMAdapter):
            async def classify(
                self,
                prompt: str,
                system_prompt: str,
                options: ClassifyOptions,
            ) -> ClassificationResult:
                return ClassificationResult(
                    action="reply",
                    type="support",
                    confidence="high",
                    raw_llm_output="",
                    fallback_applied=False,
                )

        with pytest.raises(TypeError, match="abstract method"):
            PartialAdapter()  # type: ignore[abstract]
