"""LLMAdapter ABC — provider-agnostic LLM interface.

contract-docstrings:
  Invariants: Adapter must be initialized with valid ``LLMConfig`` before
    any operation except ``test_connection()``.
  Guarantees: All returned values are fully typed (no raw ``ModelResponse``
    crosses the boundary). ``classify()`` always returns a valid
    ``ClassificationResult`` (with fallback if parsing fails).
  Errors raised: Typed exceptions from ``adapters.llm.exceptions``.
  Errors silenced: Only ``test_connection()`` silences errors.
  External state: LLM provider API (OpenAI, Anthropic, Ollama via LiteLLM).

try-except D7: External-state operations use structured try/except with
  specific exception types mapped to domain exceptions.
"""

from __future__ import annotations

import abc

from src.adapters.llm.schemas import (
    ClassificationResult,
    ClassifyOptions,
    ConnectionTestResult,
    DraftOptions,
    DraftText,
)


class LLMAdapter(abc.ABC):
    """Abstract base for LLM provider adapters.

    Implementations must handle API authentication, response extraction,
    output parsing, and structured error mapping. The adapter boundary is
    the typed schemas in ``adapters.llm.schemas`` — raw ``ModelResponse``
    never leaks past this layer.

    ``classify()`` applies an internal fallback when parsing fails:
    ``ClassificationResult(fallback_applied=True, confidence="low")``.
    ``generate_draft()`` has NO fallback — errors propagate to the caller.
    """

    @abc.abstractmethod
    async def classify(
        self,
        prompt: str,
        system_prompt: str,
        options: ClassifyOptions,
    ) -> ClassificationResult:
        """Classify an email using the LLM.

        Preconditions:
          - ``prompt`` is a non-empty string (sanitized email content).
          - ``system_prompt`` is a non-empty string with category definitions.
          - ``options.allowed_actions`` is non-empty.
          - ``options.allowed_types`` is non-empty.
          - ``options.temperature`` is in [0.0, 1.0].

        Guarantees:
          - Always returns ``ClassificationResult`` (never None).
          - If parsing fails, returns fallback with ``fallback_applied=True``,
            ``confidence="low"``, ``action="inform"``, ``type="notification"``.
          - ``raw_llm_output`` is always preserved for debugging.

        Errors raised:
          - ``ValueError`` if ``prompt`` or ``system_prompt`` is empty.
          - ``ValueError`` if ``allowed_actions`` or ``allowed_types`` is empty.
          - ``LLMConnectionError`` on network / DNS / endpoint failure.
          - ``LLMRateLimitError`` on 429 (with optional ``retry_after_seconds``).
          - ``LLMTimeoutError`` when call exceeds ``LLMConfig.timeout_seconds``.

        Errors silenced:
          - ``OutputParseError`` — captured internally, fallback applied.
        """

    @abc.abstractmethod
    async def generate_draft(
        self,
        prompt: str,
        system_prompt: str,
        options: DraftOptions,
    ) -> DraftText:
        """Generate a draft email response using the LLM.

        Preconditions:
          - ``prompt`` is a non-empty string (email content + routing context).
          - ``system_prompt`` is a non-empty string (tone and style).
          - ``options.temperature`` is in [0.0, 1.0].

        Guarantees:
          - Returns ``DraftText`` with non-empty ``content``.
          - ``model_used`` records which model produced the draft.

        Errors raised:
          - ``ValueError`` if ``prompt`` or ``system_prompt`` is empty.
          - ``LLMConnectionError`` on network / DNS / endpoint failure.
          - ``LLMRateLimitError`` on 429.
          - ``LLMTimeoutError`` when call exceeds timeout.

        Errors silenced:
          - None — draft generation failures propagate to the caller.
            There is no safe default for free-text content.
        """

    @abc.abstractmethod
    async def test_connection(self) -> ConnectionTestResult:
        """Non-destructive LLM connectivity check (health-check semantics).

        This method NEVER raises — all errors are captured into the returned
        ``ConnectionTestResult.error_detail`` field.

        Preconditions:
          - Valid ``LLMConfig`` loaded (model, api_key or base_url).

        Guarantees:
          - Always returns ``ConnectionTestResult``.
          - ``success=True`` when the provider responds.
          - ``success=False`` with ``error_detail`` otherwise.
          - ``latency_ms`` measures round-trip time.

        Errors raised: None.

        Errors silenced:
          - ALL — network, auth, and provider errors are caught and
            reflected in ``ConnectionTestResult(success=False, ...)``.
        """
