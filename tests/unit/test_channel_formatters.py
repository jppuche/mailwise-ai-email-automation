"""Unit tests for SlackBlockKitFormatter.build_blocks().

Tests cover block structure, priority rendering, truncation, sender formatting,
classification display, dashboard button, and exported priority constants.

The formatter is pure local computation — no I/O, no try/except (D8 pattern).
``get_settings`` is mocked via autouse fixture so no real Settings object is needed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.adapters.channel.formatters import (
    PRIORITY_COLORS,
    PRIORITY_EMOJIS,
    SlackBlockKitFormatter,
)
from src.adapters.channel.schemas import (
    ClassificationInfo,
    RoutingPayload,
    SenderInfo,
)

# ---------------------------------------------------------------------------
# Autouse mock for get_settings
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_settings() -> MagicMock:  # type: ignore[misc]
    settings = MagicMock()
    settings.channel_snippet_length = 150
    settings.channel_subject_max_length = 100
    with patch("src.adapters.channel.formatters.get_settings", return_value=settings):
        yield settings


# ---------------------------------------------------------------------------
# Canonical payload fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def payload() -> RoutingPayload:
    return RoutingPayload(
        email_id="email-001",
        subject="Test Subject",
        sender=SenderInfo(email="alice@example.com", name="Alice"),
        classification=ClassificationInfo(action="reply", type="support", confidence="high"),
        priority="normal",
        snippet="This is the email snippet.",
        dashboard_link="https://dashboard/emails/email-001",
        assigned_to="@jane",
        timestamp=datetime(2025, 1, 20, 10, 0, tzinfo=UTC),
    )


@pytest.fixture
def formatter() -> SlackBlockKitFormatter:
    return SlackBlockKitFormatter()


# ---------------------------------------------------------------------------
# Block structure
# ---------------------------------------------------------------------------


class TestBuildBlocksStructure:
    """Invariants about the shape of the returned block list."""

    def test_returns_four_blocks(
        self, formatter: SlackBlockKitFormatter, payload: RoutingPayload
    ) -> None:
        blocks = formatter.build_blocks(payload)
        assert len(blocks) == 4

    def test_block_types(self, formatter: SlackBlockKitFormatter, payload: RoutingPayload) -> None:
        blocks = formatter.build_blocks(payload)
        assert blocks[0]["type"] == "header"
        assert blocks[1]["type"] == "section"
        assert blocks[2]["type"] == "context"
        assert blocks[3]["type"] == "actions"

    def test_header_is_plain_text(
        self, formatter: SlackBlockKitFormatter, payload: RoutingPayload
    ) -> None:
        blocks = formatter.build_blocks(payload)
        header_text = blocks[0]["text"]
        assert isinstance(header_text, dict)
        assert header_text["type"] == "plain_text"

    def test_section_has_four_fields(
        self, formatter: SlackBlockKitFormatter, payload: RoutingPayload
    ) -> None:
        blocks = formatter.build_blocks(payload)
        fields = blocks[1]["fields"]
        assert isinstance(fields, list)
        assert len(fields) == 4


# ---------------------------------------------------------------------------
# Priority rendering
# ---------------------------------------------------------------------------


class TestPriorityRendering:
    """Header text must embed the correct emoji and uppercase priority label."""

    def test_urgent_emoji_and_label(
        self, formatter: SlackBlockKitFormatter, payload: RoutingPayload
    ) -> None:
        payload = payload.model_copy(update={"priority": "urgent"})
        blocks = formatter.build_blocks(payload)
        header_text = str(blocks[0]["text"])
        assert ":red_circle:" in header_text
        assert "[URGENT]" in header_text

    def test_normal_emoji_and_label(
        self, formatter: SlackBlockKitFormatter, payload: RoutingPayload
    ) -> None:
        blocks = formatter.build_blocks(payload)  # default priority is "normal"
        header_text = str(blocks[0]["text"])
        assert ":large_blue_circle:" in header_text
        assert "[NORMAL]" in header_text

    def test_low_emoji_and_label(
        self, formatter: SlackBlockKitFormatter, payload: RoutingPayload
    ) -> None:
        payload = payload.model_copy(update={"priority": "low"})
        blocks = formatter.build_blocks(payload)
        header_text = str(blocks[0]["text"])
        assert ":white_circle:" in header_text
        assert "[LOW]" in header_text


# ---------------------------------------------------------------------------
# Assigned-to rendering
# ---------------------------------------------------------------------------


class TestAssignedTo:
    """Section field 'Assigned to' respects the assigned_to value or its absence."""

    def _assigned_field_text(self, blocks: list[dict[str, object]]) -> str:
        fields = blocks[1]["fields"]
        assert isinstance(fields, list)
        for field in fields:
            assert isinstance(field, dict)
            text = str(field.get("text", ""))
            if "*Assigned to:*" in text:
                return text
        raise AssertionError("Assigned-to field not found in section blocks")

    def test_assigned_to_present(
        self, formatter: SlackBlockKitFormatter, payload: RoutingPayload
    ) -> None:
        blocks = formatter.build_blocks(payload)
        text = self._assigned_field_text(blocks)
        assert "@jane" in text

    def test_assigned_to_none_shows_unassigned(
        self, formatter: SlackBlockKitFormatter, payload: RoutingPayload
    ) -> None:
        payload = payload.model_copy(update={"assigned_to": None})
        blocks = formatter.build_blocks(payload)
        text = self._assigned_field_text(blocks)
        assert "Unassigned" in text


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------


class TestTruncation:
    """Subject and snippet are sliced to their configured max lengths."""

    def _header_text(self, blocks: list[dict[str, object]]) -> str:
        header = blocks[0]["text"]
        assert isinstance(header, dict)
        return str(header["text"])

    def _context_text(self, blocks: list[dict[str, object]]) -> str:
        elements = blocks[2]["elements"]
        assert isinstance(elements, list)
        assert len(elements) == 1
        assert isinstance(elements[0], dict)
        return str(elements[0]["text"])

    def test_subject_truncation(
        self,
        formatter: SlackBlockKitFormatter,
        payload: RoutingPayload,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.channel_subject_max_length = 10
        long_subject = "A" * 20
        payload = payload.model_copy(update={"subject": long_subject})
        blocks = formatter.build_blocks(payload)
        header_text = self._header_text(blocks)
        assert "A" * 10 in header_text
        assert "A" * 11 not in header_text

    def test_subject_within_limit_not_truncated(
        self, formatter: SlackBlockKitFormatter, payload: RoutingPayload
    ) -> None:
        short_subject = "Short"
        payload = payload.model_copy(update={"subject": short_subject})
        blocks = formatter.build_blocks(payload)
        header_text = self._header_text(blocks)
        assert "Short" in header_text

    def test_snippet_truncation(
        self,
        formatter: SlackBlockKitFormatter,
        payload: RoutingPayload,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.channel_snippet_length = 10
        long_snippet = "B" * 20
        payload = payload.model_copy(update={"snippet": long_snippet})
        blocks = formatter.build_blocks(payload)
        context_text = self._context_text(blocks)
        assert "B" * 10 in context_text
        assert "B" * 11 not in context_text

    def test_snippet_within_limit_not_truncated(
        self, formatter: SlackBlockKitFormatter, payload: RoutingPayload
    ) -> None:
        short_snippet = "Short snippet."
        payload = payload.model_copy(update={"snippet": short_snippet})
        blocks = formatter.build_blocks(payload)
        context_text = self._context_text(blocks)
        assert "Short snippet." in context_text

    def test_custom_truncation_lengths(
        self,
        formatter: SlackBlockKitFormatter,
        payload: RoutingPayload,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.channel_subject_max_length = 5
        mock_settings.channel_snippet_length = 8
        payload = payload.model_copy(update={"subject": "X" * 20, "snippet": "Y" * 20})
        blocks = formatter.build_blocks(payload)
        header_text = self._header_text(blocks)
        context_text = self._context_text(blocks)
        assert "X" * 5 in header_text
        assert "X" * 6 not in header_text
        assert "Y" * 8 in context_text
        assert "Y" * 9 not in context_text


# ---------------------------------------------------------------------------
# Sender formatting
# ---------------------------------------------------------------------------


class TestSenderFormatting:
    """From field renders name + email when name is present, email-only otherwise."""

    def _from_field_text(self, blocks: list[dict[str, object]]) -> str:
        fields = blocks[1]["fields"]
        assert isinstance(fields, list)
        for field in fields:
            assert isinstance(field, dict)
            text = str(field.get("text", ""))
            if "*From:*" in text:
                return text
        raise AssertionError("From field not found in section blocks")

    def test_sender_with_name(
        self, formatter: SlackBlockKitFormatter, payload: RoutingPayload
    ) -> None:
        blocks = formatter.build_blocks(payload)
        text = self._from_field_text(blocks)
        assert "Alice <alice@example.com>" in text

    def test_sender_without_name(
        self, formatter: SlackBlockKitFormatter, payload: RoutingPayload
    ) -> None:
        payload = payload.model_copy(
            update={"sender": SenderInfo(email="bob@example.com", name=None)}
        )
        blocks = formatter.build_blocks(payload)
        text = self._from_field_text(blocks)
        assert "bob@example.com" in text
        assert "<" not in text


# ---------------------------------------------------------------------------
# Classification field
# ---------------------------------------------------------------------------


class TestClassificationField:
    """Classification field format is 'action / type'."""

    def _classification_field_text(self, blocks: list[dict[str, object]]) -> str:
        fields = blocks[1]["fields"]
        assert isinstance(fields, list)
        for field in fields:
            assert isinstance(field, dict)
            text = str(field.get("text", ""))
            if "*Classification:*" in text:
                return text
        raise AssertionError("Classification field not found in section blocks")

    def test_classification_format(
        self, formatter: SlackBlockKitFormatter, payload: RoutingPayload
    ) -> None:
        blocks = formatter.build_blocks(payload)
        text = self._classification_field_text(blocks)
        assert "reply / support" in text


# ---------------------------------------------------------------------------
# Dashboard button
# ---------------------------------------------------------------------------


class TestDashboardButton:
    """Actions block contains a single primary button linking to dashboard_link."""

    def _button(self, blocks: list[dict[str, object]]) -> dict[str, object]:
        elements = blocks[3]["elements"]
        assert isinstance(elements, list)
        assert len(elements) == 1
        button = elements[0]
        assert isinstance(button, dict)
        return button

    def test_button_url(self, formatter: SlackBlockKitFormatter, payload: RoutingPayload) -> None:
        blocks = formatter.build_blocks(payload)
        button = self._button(blocks)
        assert button["url"] == "https://dashboard/emails/email-001"

    def test_button_text(self, formatter: SlackBlockKitFormatter, payload: RoutingPayload) -> None:
        blocks = formatter.build_blocks(payload)
        button = self._button(blocks)
        button_text = button["text"]
        assert isinstance(button_text, dict)
        assert button_text["text"] == "View in Dashboard"

    def test_button_style_primary(
        self, formatter: SlackBlockKitFormatter, payload: RoutingPayload
    ) -> None:
        blocks = formatter.build_blocks(payload)
        button = self._button(blocks)
        assert button["style"] == "primary"


# ---------------------------------------------------------------------------
# Exported priority constants
# ---------------------------------------------------------------------------


class TestPriorityConstants:
    """PRIORITY_COLORS and PRIORITY_EMOJIS are exported with all three priority keys."""

    def test_priority_colors_keys(self) -> None:
        assert "urgent" in PRIORITY_COLORS
        assert "normal" in PRIORITY_COLORS
        assert "low" in PRIORITY_COLORS

    def test_priority_emojis_keys(self) -> None:
        assert "urgent" in PRIORITY_EMOJIS
        assert "normal" in PRIORITY_EMOJIS
        assert "low" in PRIORITY_EMOJIS
