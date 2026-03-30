"""LLM adapter package — provider-agnostic LLM interface.

Public API:
  - ``LLMAdapter`` ABC and ``LiteLLMAdapter`` concrete implementation
  - Typed schemas: ``ClassificationResult``, ``DraftText``, etc.
  - Exception hierarchy rooted at ``LLMAdapterError``
"""

from src.adapters.llm.base import LLMAdapter
from src.adapters.llm.exceptions import (
    LLMAdapterError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMTimeoutError,
    OutputParseError,
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

__all__ = [
    "ClassificationResult",
    "ClassifyOptions",
    "ConnectionTestResult",
    "DraftOptions",
    "DraftText",
    "LLMAdapter",
    "LLMAdapterError",
    "LLMConfig",
    "LLMConnectionError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LiteLLMAdapter",
    "OutputParseError",
]
