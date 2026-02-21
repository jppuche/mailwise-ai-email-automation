"""LiteLLMAdapter — concrete LLMAdapter using litellm.acompletion.

contract-docstrings:
  Invariants: ``LLMConfig`` must be provided at construction with valid
    model names and optional API credentials.
  Guarantees: ``ModelResponse`` never escapes this module. All returns are
    typed adapter schemas. ``classify()`` always returns (with fallback).
  Errors raised: Typed ``LLMAdapterError`` subclasses.
  Errors silenced: ``test_connection()`` silences all errors.
    ``classify()`` silences parse failures (fallback applied).
  External state: LLM provider API via LiteLLM.

try-except D7: ``litellm.acompletion`` calls use structured try/except
  mapping to domain exceptions.
try-except D8: Argument validation uses conditionals, not try/except.
"""

from __future__ import annotations

import time

import litellm
import litellm.exceptions as litellm_exc
import structlog

from src.adapters.llm.base import LLMAdapter
from src.adapters.llm.exceptions import (
    LLMConnectionError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from src.adapters.llm.parser import parse_classification
from src.adapters.llm.schemas import (
    ClassificationResult,
    ClassifyOptions,
    ConnectionTestResult,
    DraftOptions,
    DraftText,
    LLMConfig,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class LiteLLMAdapter(LLMAdapter):
    """LiteLLM-backed adapter supporting OpenAI, Anthropic, and Ollama.

    All ``ModelResponse`` extraction happens inside this class. The typed
    schemas in ``adapters.llm.schemas`` are the only values that cross the
    adapter boundary.
    """

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        # Configure litellm globals if credentials provided
        if config.api_key:
            litellm.api_key = config.api_key
        if config.base_url:
            litellm.api_base = config.base_url

    async def classify(
        self,
        prompt: str,
        system_prompt: str,
        options: ClassifyOptions,
    ) -> ClassificationResult:
        """Classify an email using the configured LLM.

        Preconditions:
          - ``prompt`` is a non-empty string.
          - ``system_prompt`` is a non-empty string.
          - ``options.allowed_actions`` is non-empty.
          - ``options.allowed_types`` is non-empty.

        Guarantees:
          - Always returns ``ClassificationResult`` (never None).
          - If parse fails, fallback: action="inform", type="notification",
            confidence="low", fallback_applied=True.
          - ``raw_llm_output`` always preserved.

        Errors raised:
          - ``ValueError`` for empty prompt/system_prompt.
          - ``LLMConnectionError``, ``LLMRateLimitError``, ``LLMTimeoutError``.

        Errors silenced:
          - Parse failure — fallback applied, OutputParseError not re-raised.
        """
        # Precondition validation (D8: conditionals, not try/except)
        if not prompt:
            raise ValueError("prompt must not be empty")
        if not system_prompt:
            raise ValueError("system_prompt must not be empty")
        if not options.allowed_actions:
            raise ValueError("allowed_actions must not be empty")
        if not options.allowed_types:
            raise ValueError("allowed_types must not be empty")

        model = options.model or self._config.classify_model

        # External-state operation (D7: structured try/except)
        try:
            response = await litellm.acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=options.temperature,
                max_tokens=options.max_tokens,
                timeout=self._config.timeout_seconds,
            )
        except litellm_exc.RateLimitError as exc:
            raise LLMRateLimitError(
                str(exc),
                original_error=exc,
            ) from exc
        except litellm_exc.Timeout as exc:
            raise LLMTimeoutError(
                str(exc),
                original_error=exc,
            ) from exc
        except litellm_exc.APIConnectionError as exc:
            raise LLMConnectionError(
                str(exc),
                original_error=exc,
            ) from exc

        # Extract content from ModelResponse (never escapes this method)
        raw_output: str = response.choices[0].message.content or ""

        # Parse — local computation (D8: conditionals in parser)
        result = parse_classification(
            raw_output,
            options.allowed_actions,
            options.allowed_types,
        )

        if result is None:
            # Fallback (Cat 4 pre-mortem: documented parse failure path)
            logger.warning(
                "llm_parse_fallback",
                model=model,
                raw_output_preview=raw_output[:200],
            )
            return ClassificationResult(
                action="inform",
                type="notification",
                confidence="low",
                raw_llm_output=raw_output,
                fallback_applied=True,
            )

        return result

    async def generate_draft(
        self,
        prompt: str,
        system_prompt: str,
        options: DraftOptions,
    ) -> DraftText:
        """Generate a draft email response using the configured LLM.

        Preconditions:
          - ``prompt`` is a non-empty string.
          - ``system_prompt`` is a non-empty string.

        Guarantees:
          - Returns ``DraftText`` with ``model_used`` populated.
          - NO fallback — errors propagate to caller (no safe default).

        Errors raised:
          - ``ValueError`` for empty prompt/system_prompt.
          - ``LLMConnectionError``, ``LLMRateLimitError``, ``LLMTimeoutError``.

        Errors silenced: None.
        """
        # Precondition validation (D8)
        if not prompt:
            raise ValueError("prompt must not be empty")
        if not system_prompt:
            raise ValueError("system_prompt must not be empty")

        model = options.model or self._config.draft_model

        # External-state operation (D7)
        try:
            response = await litellm.acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=options.temperature,
                max_tokens=options.max_tokens,
                timeout=self._config.timeout_seconds,
            )
        except litellm_exc.RateLimitError as exc:
            raise LLMRateLimitError(
                str(exc),
                original_error=exc,
            ) from exc
        except litellm_exc.Timeout as exc:
            raise LLMTimeoutError(
                str(exc),
                original_error=exc,
            ) from exc
        except litellm_exc.APIConnectionError as exc:
            raise LLMConnectionError(
                str(exc),
                original_error=exc,
            ) from exc

        # No fallback for drafts — errors propagate (no safe default)
        content: str = response.choices[0].message.content or ""

        return DraftText(
            content=content,
            model_used=model,
            fallback_applied=False,
        )

    async def test_connection(self) -> ConnectionTestResult:
        """Non-destructive LLM connectivity check (health-check semantics).

        Silences ALL errors — returns ConnectionTestResult(success=False, ...)
        on any failure. Measures round-trip latency in milliseconds.
        """
        model = self._config.classify_model
        start = time.monotonic()

        try:
            await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
                timeout=self._config.timeout_seconds,
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            return ConnectionTestResult(
                success=True,
                model_used=model,
                latency_ms=latency_ms,
            )
        except Exception as exc:  # noqa: BLE001 — health-check silences ALL errors
            latency_ms = int((time.monotonic() - start) * 1000)
            return ConnectionTestResult(
                success=False,
                model_used=model,
                latency_ms=latency_ms,
                error_detail=str(exc),
            )
