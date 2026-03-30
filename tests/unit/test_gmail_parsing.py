"""Unit tests for Gmail MIME parsing helpers.

Tests the private parsing functions in gmail.py using raw Gmail API
response dict fixtures. No network calls, no ``build()`` invocation.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime

import pytest

from src.adapters.email.gmail import (
    _extract_attachments,
    _extract_body,
    _get_header,
    _parse_address,
    _parse_address_list,
    _parse_date,
    _parse_message,
)

# ---------------------------------------------------------------------------
# Fixtures — raw Gmail API response dicts
# ---------------------------------------------------------------------------

_SIMPLE_TEXT_MESSAGE: dict = {
    "id": "msg001",
    "threadId": "thread001",
    "labelIds": ["INBOX", "UNREAD"],
    "snippet": "Hello world",
    "payload": {
        "mimeType": "text/plain",
        "headers": [
            {"name": "From", "value": "Alice <alice@example.com>"},
            {"name": "To", "value": "bob@example.com"},
            {"name": "Subject", "value": "Test Subject"},
            {"name": "Date", "value": "Mon, 20 Jan 2025 10:00:00 +0000"},
        ],
        "body": {
            "data": base64.urlsafe_b64encode(b"Hello world").decode(),
        },
        "parts": [],
    },
}

_MULTIPART_MESSAGE: dict = {
    "id": "msg002",
    "threadId": "thread002",
    "labelIds": ["INBOX"],
    "snippet": "Multipart",
    "payload": {
        "mimeType": "multipart/alternative",
        "headers": [
            {"name": "From", "value": "sender@example.com"},
            {"name": "To", "value": "rcpt@example.com"},
            {"name": "Subject", "value": "Multipart Subject"},
            {"name": "Date", "value": "Tue, 21 Jan 2025 12:00:00 +0000"},
        ],
        "body": {},
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {
                    "data": base64.urlsafe_b64encode(b"Plain body").decode(),
                },
                "parts": [],
            },
            {
                "mimeType": "text/html",
                "body": {
                    "data": base64.urlsafe_b64encode(b"<p>HTML body</p>").decode(),
                },
                "parts": [],
            },
        ],
    },
}

_MESSAGE_WITH_ATTACHMENT: dict = {
    "id": "msg003",
    "threadId": "thread003",
    "labelIds": ["INBOX"],
    "snippet": "See attached",
    "payload": {
        "mimeType": "multipart/mixed",
        "headers": [
            {"name": "From", "value": "attach@example.com"},
            {"name": "To", "value": "rcpt@example.com"},
            {"name": "Subject", "value": "With Attachment"},
            {"name": "Date", "value": "Wed, 22 Jan 2025 08:00:00 +0000"},
        ],
        "body": {},
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {
                    "data": base64.urlsafe_b64encode(b"See attached").decode(),
                },
                "parts": [],
            },
            {
                "mimeType": "application/pdf",
                "filename": "report.pdf",
                "body": {
                    "size": 4096,
                    "attachmentId": "att_001",
                },
                "parts": [],
            },
        ],
    },
}

_MESSAGE_NO_THREAD: dict = {
    "id": "msg004",
    "labelIds": ["INBOX"],
    "snippet": "No thread",
    "payload": {
        "mimeType": "text/plain",
        "headers": [
            {"name": "From", "value": "solo@example.com"},
            {"name": "To", "value": "rcpt@example.com"},
            {"name": "Date", "value": "Thu, 23 Jan 2025 09:00:00 +0000"},
        ],
        "body": {
            "data": base64.urlsafe_b64encode(b"No thread").decode(),
        },
        "parts": [],
    },
}


# ---------------------------------------------------------------------------
# _get_header
# ---------------------------------------------------------------------------


class TestGetHeader:
    def test_existing_header(self) -> None:
        headers = [{"name": "Subject", "value": "Hello"}]
        assert _get_header(headers, "Subject") == "Hello"

    def test_case_insensitive(self) -> None:
        headers = [{"name": "FROM", "value": "alice@example.com"}]
        assert _get_header(headers, "from") == "alice@example.com"

    def test_missing_header(self) -> None:
        headers = [{"name": "Subject", "value": "Hello"}]
        assert _get_header(headers, "Cc") == ""

    def test_empty_headers(self) -> None:
        assert _get_header([], "Subject") == ""


# ---------------------------------------------------------------------------
# _parse_address / _parse_address_list
# ---------------------------------------------------------------------------


class TestParseAddress:
    def test_with_display_name(self) -> None:
        r = _parse_address("Alice <alice@example.com>")
        assert r["email"] == "alice@example.com"
        assert r["name"] == "Alice"

    def test_bare_email(self) -> None:
        r = _parse_address("bob@example.com")
        assert r["email"] == "bob@example.com"
        assert r["name"] is None

    def test_quoted_display_name(self) -> None:
        r = _parse_address('"Alice Bob" <ab@example.com>')
        assert r["email"] == "ab@example.com"
        assert r["name"] == "Alice Bob"


class TestParseAddressList:
    def test_single_address(self) -> None:
        result = _parse_address_list("alice@example.com")
        assert len(result) == 1
        assert result[0]["email"] == "alice@example.com"

    def test_multiple_addresses(self) -> None:
        result = _parse_address_list("alice@example.com, Bob <bob@example.com>")
        assert len(result) == 2
        assert result[0]["email"] == "alice@example.com"
        assert result[1]["email"] == "bob@example.com"

    def test_empty_string(self) -> None:
        assert _parse_address_list("") == []


# ---------------------------------------------------------------------------
# _extract_body
# ---------------------------------------------------------------------------


class TestExtractBody:
    def test_plain_text_only(self) -> None:
        payload = _SIMPLE_TEXT_MESSAGE["payload"]
        plain, html = _extract_body(payload)
        assert plain == "Hello world"
        assert html is None

    def test_multipart_both(self) -> None:
        payload = _MULTIPART_MESSAGE["payload"]
        plain, html = _extract_body(payload)
        assert plain == "Plain body"
        assert html == "<p>HTML body</p>"

    def test_empty_body(self) -> None:
        payload = {"mimeType": "text/plain", "body": {}, "parts": []}
        plain, html = _extract_body(payload)
        assert plain is None
        assert html is None


# ---------------------------------------------------------------------------
# _extract_attachments
# ---------------------------------------------------------------------------


class TestExtractAttachments:
    def test_with_attachment(self) -> None:
        payload = _MESSAGE_WITH_ATTACHMENT["payload"]
        attachments = _extract_attachments(payload)
        assert len(attachments) == 1
        assert attachments[0]["filename"] == "report.pdf"
        assert attachments[0]["mime_type"] == "application/pdf"
        assert attachments[0]["size_bytes"] == 4096
        assert attachments[0]["attachment_id"] == "att_001"

    def test_no_attachments(self) -> None:
        payload = _SIMPLE_TEXT_MESSAGE["payload"]
        assert _extract_attachments(payload) == []


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------


class TestParseDate:
    def test_rfc2822_date(self) -> None:
        dt = _parse_date("Mon, 20 Jan 2025 10:00:00 +0000")
        assert dt.year == 2025
        assert dt.month == 1
        assert dt.day == 20
        assert dt.tzinfo is not None

    def test_empty_string_returns_utc_now(self) -> None:
        dt = _parse_date("")
        assert dt.tzinfo is not None
        assert (datetime.now(tz=UTC) - dt).total_seconds() < 5


# ---------------------------------------------------------------------------
# _parse_message (full message parsing)
# ---------------------------------------------------------------------------


class TestParseMessage:
    def test_simple_message(self) -> None:
        msg = _parse_message(_SIMPLE_TEXT_MESSAGE)
        assert msg.id == "msg001"
        assert msg.gmail_message_id == "msg001"
        assert msg.thread_id == "thread001"
        assert msg.subject == "Test Subject"
        assert msg.from_address == "alice@example.com"
        assert msg.body_plain == "Hello world"
        assert msg.snippet == "Hello world"
        assert msg.received_at.tzinfo is not None
        assert "INBOX" in msg.provider_labels
        assert msg.raw_headers["Subject"] == "Test Subject"

    def test_multipart_message(self) -> None:
        msg = _parse_message(_MULTIPART_MESSAGE)
        assert msg.body_plain == "Plain body"
        assert msg.body_html == "<p>HTML body</p>"

    def test_message_with_attachment(self) -> None:
        msg = _parse_message(_MESSAGE_WITH_ATTACHMENT)
        assert len(msg.attachments) == 1
        assert msg.attachments[0]["filename"] == "report.pdf"

    def test_message_no_thread_id(self) -> None:
        msg = _parse_message(_MESSAGE_NO_THREAD)
        assert msg.thread_id is None

    def test_to_addresses_parsed(self) -> None:
        msg = _parse_message(_SIMPLE_TEXT_MESSAGE)
        assert len(msg.to_addresses) == 1
        assert msg.to_addresses[0]["email"] == "bob@example.com"

    def test_missing_payload_raises(self) -> None:
        with pytest.raises(KeyError):
            _parse_message({"id": "bad"})
