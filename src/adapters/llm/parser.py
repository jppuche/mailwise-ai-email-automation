"""LLM output parser — extracts ClassificationResult from raw LLM output.

Pure local computation. All logic uses conditionals except
``_safe_json_loads`` (json.loads has no conditional alternative).

Handles 7 documented output shapes:
  1. Pure JSON
  2. JSON in markdown code block
  3. Explanatory text around JSON
  4. Wrong casing in values
  5. Thinking-mode tags before JSON
  6. Extra fields (Pydantic extra="ignore")
  7. Alternate key names

Returns ``ClassificationResult | None``. Never raises. Caller applies
fallback on ``None``.
"""

from __future__ import annotations

import json
import re

from src.adapters.llm.schemas import ClassificationResult

# Key name aliases: LLMs sometimes use alternate field names
_ACTION_KEYS = ("action", "intent", "category")
_TYPE_KEYS = ("type", "email_type", "classification")

# Regex patterns (compiled once)
_THINKING_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_MARKDOWN_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\}")


def parse_classification(
    raw: str,
    allowed_actions: list[str],
    allowed_types: list[str],
) -> ClassificationResult | None:
    """Extract ClassificationResult from raw LLM output.

    Returns None if parsing fails — the adapter applies fallback.
    Never raises exceptions (local computation, conditionals only).
    """
    if not raw or not raw.strip():
        return None

    text = _strip_thinking_tags(raw)
    text = _strip_markdown_fences(text)
    json_str = _extract_json_object(text)

    if json_str is None:
        return None

    data = _safe_json_loads(json_str)
    if data is None:
        return None

    action = _resolve_field(data, _ACTION_KEYS)
    type_ = _resolve_field(data, _TYPE_KEYS)

    if action is None or type_ is None:
        return None

    action = action.lower()
    type_ = type_.lower()

    if action not in allowed_actions or type_ not in allowed_types:
        return None

    return ClassificationResult(
        action=action,
        type=type_,
        confidence="high",
        raw_llm_output=raw,
        fallback_applied=False,
    )


def _strip_thinking_tags(text: str) -> str:
    """Remove <think>...</think> blocks from thinking-mode models."""
    return _THINKING_TAG_RE.sub("", text).strip()


def _strip_markdown_fences(text: str) -> str:
    """Extract content from markdown code fences if present."""
    match = _MARKDOWN_FENCE_RE.search(text)
    if match is not None:
        return match.group(1).strip()
    return text


def _extract_json_object(text: str) -> str | None:
    """Extract the first JSON object {...} from text."""
    # Try the full text as JSON first (shape 1: pure JSON)
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    # Extract first {...} from surrounding text (shape 3)
    match = _JSON_OBJECT_RE.search(text)
    if match is not None:
        return match.group(0)

    return None


def _safe_json_loads(text: str) -> dict[str, object] | None:
    """Parse JSON string to dict. Returns None on failure.

    Note: json.loads has no conditional alternative — structured
    try/except is the only option for JSON parse failure detection.
    """
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _resolve_field(
    data: dict[str, object],
    keys: tuple[str, ...],
) -> str | None:
    """Resolve a field value from a dict using multiple possible key names."""
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
