"""Unit tests for the LLM output parser.

Tests all 7 documented output shapes (Cat 4 pre-mortem) plus edge cases.
The parser is pure local computation — no mocks or external dependencies.
"""

from __future__ import annotations

from src.adapters.llm.parser import parse_classification

ACTIONS = ["reply", "forward", "inform", "archive"]
TYPES = ["support", "sales", "notification", "internal"]


# ---------------------------------------------------------------------------
# Shape 1: Pure JSON
# ---------------------------------------------------------------------------


class TestPureJson:
    """Shape 1 — raw output is valid JSON object."""

    def test_valid_json(self) -> None:
        raw = '{"action": "reply", "type": "support"}'
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.action == "reply"
        assert result.type == "support"
        assert result.confidence == "high"
        assert result.fallback_applied is False

    def test_preserves_raw_output(self) -> None:
        raw = '{"action": "reply", "type": "support"}'
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.raw_llm_output == raw


# ---------------------------------------------------------------------------
# Shape 2: JSON in markdown code block
# ---------------------------------------------------------------------------


class TestMarkdownFences:
    """Shape 2 — JSON wrapped in markdown code fences."""

    def test_json_code_block(self) -> None:
        raw = '```json\n{"action": "forward", "type": "sales"}\n```'
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.action == "forward"
        assert result.type == "sales"

    def test_plain_code_block(self) -> None:
        raw = '```\n{"action": "reply", "type": "support"}\n```'
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.action == "reply"


# ---------------------------------------------------------------------------
# Shape 3: Explanatory text around JSON
# ---------------------------------------------------------------------------


class TestTextAroundJson:
    """Shape 3 — LLM explains before/after the JSON."""

    def test_text_before_json(self) -> None:
        raw = (
            'Based on the email content, here is my classification:\n'
            '{"action": "reply", "type": "support"}\nThis is a support request.'
        )
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.action == "reply"

    def test_text_after_json(self) -> None:
        raw = (
            '{"action": "inform", "type": "notification"}\n'
            'The above classification is based on...'
        )
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.action == "inform"


# ---------------------------------------------------------------------------
# Shape 4: Wrong casing in values
# ---------------------------------------------------------------------------


class TestWrongCasing:
    """Shape 4 — LLM returns values with wrong casing."""

    def test_uppercase_values(self) -> None:
        raw = '{"action": "REPLY", "type": "SUPPORT"}'
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.action == "reply"
        assert result.type == "support"

    def test_mixed_case_values(self) -> None:
        raw = '{"action": "Forward", "type": "Sales"}'
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.action == "forward"
        assert result.type == "sales"


# ---------------------------------------------------------------------------
# Shape 5: Thinking-mode tags
# ---------------------------------------------------------------------------


class TestThinkingTags:
    """Shape 5 — thinking-mode models emit <think> blocks."""

    def test_thinking_tags_stripped(self) -> None:
        raw = (
            '<think>The email asks about pricing, so this is sales.</think>\n'
            '{"action": "reply", "type": "sales"}'
        )
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.action == "reply"
        assert result.type == "sales"

    def test_multiline_thinking(self) -> None:
        raw = (
            '<think>\nLet me analyze...\nThis is a support request.\n</think>\n'
            '{"action": "reply", "type": "support"}'
        )
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.action == "reply"


# ---------------------------------------------------------------------------
# Shape 6: Extra fields ignored
# ---------------------------------------------------------------------------


class TestExtraFields:
    """Shape 6 — LLM adds fields not in the schema."""

    def test_extra_fields_dropped(self) -> None:
        raw = (
            '{"action": "reply", "type": "support",'
            ' "explanation": "This is a support request", "priority": "high"}'
        )
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.action == "reply"
        assert not hasattr(result, "explanation")


# ---------------------------------------------------------------------------
# Shape 7: Alternate key names
# ---------------------------------------------------------------------------


class TestAlternateKeyNames:
    """Shape 7 — LLM uses alternate field names."""

    def test_intent_instead_of_action(self) -> None:
        raw = '{"intent": "reply", "type": "support"}'
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.action == "reply"

    def test_category_instead_of_action(self) -> None:
        raw = '{"category": "forward", "type": "sales"}'
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.action == "forward"

    def test_email_type_instead_of_type(self) -> None:
        raw = '{"action": "reply", "email_type": "support"}'
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.type == "support"

    def test_classification_instead_of_type(self) -> None:
        raw = '{"action": "reply", "classification": "notification"}'
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.type == "notification"


# ---------------------------------------------------------------------------
# Combined shapes
# ---------------------------------------------------------------------------


class TestCombinedShapes:
    """Multiple shapes combined in a single output."""

    def test_thinking_plus_markdown_plus_wrong_case(self) -> None:
        raw = '<think>Analyzing...</think>\n```json\n{"action": "REPLY", "type": "Support"}\n```'
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.action == "reply"
        assert result.type == "support"

    def test_thinking_plus_extra_fields(self) -> None:
        raw = (
            '<think>This is sales.</think>\n'
            '{"action": "forward", "type": "sales", "reason": "pricing inquiry"}'
        )
        result = parse_classification(raw, ACTIONS, TYPES)
        assert result is not None
        assert result.action == "forward"


# ---------------------------------------------------------------------------
# Failure cases — returns None
# ---------------------------------------------------------------------------


class TestFailureCases:
    """Parser returns None on unparseable input."""

    def test_empty_string(self) -> None:
        assert parse_classification("", ACTIONS, TYPES) is None

    def test_whitespace_only(self) -> None:
        assert parse_classification("   \n\t  ", ACTIONS, TYPES) is None

    def test_no_json(self) -> None:
        assert parse_classification("This is just plain text", ACTIONS, TYPES) is None

    def test_invalid_json(self) -> None:
        assert parse_classification("{broken json", ACTIONS, TYPES) is None

    def test_json_array_not_object(self) -> None:
        assert parse_classification('[{"action": "reply"}]', ACTIONS, TYPES) is None

    def test_missing_action_field(self) -> None:
        raw = '{"type": "support"}'
        assert parse_classification(raw, ACTIONS, TYPES) is None

    def test_missing_type_field(self) -> None:
        raw = '{"action": "reply"}'
        assert parse_classification(raw, ACTIONS, TYPES) is None

    def test_action_not_in_allowed(self) -> None:
        raw = '{"action": "delete", "type": "support"}'
        assert parse_classification(raw, ACTIONS, TYPES) is None

    def test_type_not_in_allowed(self) -> None:
        raw = '{"action": "reply", "type": "spam"}'
        assert parse_classification(raw, ACTIONS, TYPES) is None

    def test_empty_action_value(self) -> None:
        raw = '{"action": "", "type": "support"}'
        assert parse_classification(raw, ACTIONS, TYPES) is None

    def test_non_string_action_value(self) -> None:
        raw = '{"action": 123, "type": "support"}'
        assert parse_classification(raw, ACTIONS, TYPES) is None
