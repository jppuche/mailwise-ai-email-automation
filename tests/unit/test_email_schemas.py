"""Unit tests for email adapter boundary schemas.

Validates Pydantic models, TypedDicts, and the DraftId NewType.
No external dependencies — pure schema validation.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.adapters.email.schemas import (
    AttachmentData,
    ConnectionStatus,
    ConnectionTestResult,
    DraftId,
    EmailCredentials,
    EmailMessage,
    Label,
    RecipientData,
)

# ---------------------------------------------------------------------------
# EmailMessage
# ---------------------------------------------------------------------------


class TestEmailMessage:
    """Validates EmailMessage construction and field constraints."""

    def _make_message(self, **overrides: object) -> EmailMessage:
        defaults: dict[str, object] = {
            "id": "msg001",
            "gmail_message_id": "msg001",
            "subject": "Hello",
            "from_address": "alice@example.com",
            "received_at": datetime(2025, 1, 20, 10, 0, tzinfo=UTC),
        }
        defaults.update(overrides)
        return EmailMessage(**defaults)  # type: ignore[arg-type]

    def test_valid_full_construction(self) -> None:
        msg = self._make_message(
            thread_id="thread001",
            to_addresses=[RecipientData(email="bob@example.com", name="Bob")],
            cc_addresses=[RecipientData(email="cc@example.com", name=None)],
            body_plain="Hello world",
            body_html="<p>Hello</p>",
            snippet="Hello world",
            attachments=[
                AttachmentData(
                    filename="doc.pdf",
                    mime_type="application/pdf",
                    size_bytes=1024,
                    attachment_id="att001",
                )
            ],
            raw_headers={"From": "alice@example.com"},
            provider_labels=["INBOX", "UNREAD"],
        )
        assert msg.id == "msg001"
        assert msg.gmail_message_id == "msg001"
        assert msg.thread_id == "thread001"
        assert len(msg.to_addresses) == 1
        assert msg.to_addresses[0]["email"] == "bob@example.com"
        assert msg.body_plain == "Hello world"
        assert msg.attachments[0]["filename"] == "doc.pdf"

    def test_minimal_construction(self) -> None:
        msg = self._make_message()
        assert msg.body_plain is None
        assert msg.body_html is None
        assert msg.snippet is None
        assert msg.thread_id is None
        assert msg.to_addresses == []
        assert msg.cc_addresses == []
        assert msg.attachments == []
        assert msg.raw_headers == {}
        assert msg.provider_labels == []

    def test_received_at_naive_gets_utc(self) -> None:
        naive = datetime(2025, 1, 20, 10, 0)  # noqa: DTZ001
        msg = self._make_message(received_at=naive)
        assert msg.received_at.tzinfo is not None
        assert msg.received_at.tzinfo == UTC

    def test_received_at_aware_preserved(self) -> None:
        aware = datetime(2025, 1, 20, 10, 0, tzinfo=UTC)
        msg = self._make_message(received_at=aware)
        assert msg.received_at == aware

    def test_missing_required_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            EmailMessage(
                gmail_message_id="msg001",
                from_address="a@b.com",
                received_at=datetime.now(tz=UTC),
            )  # type: ignore[call-arg]

    def test_missing_required_from_address_raises(self) -> None:
        with pytest.raises(ValidationError):
            EmailMessage(
                id="msg001",
                gmail_message_id="msg001",
                received_at=datetime.now(tz=UTC),
            )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# RecipientData / AttachmentData (TypedDicts)
# ---------------------------------------------------------------------------


class TestRecipientData:
    def test_with_name(self) -> None:
        r = RecipientData(email="bob@example.com", name="Bob")
        assert r["email"] == "bob@example.com"
        assert r["name"] == "Bob"

    def test_with_none_name(self) -> None:
        r = RecipientData(email="bob@example.com", name=None)
        assert r["name"] is None

    def test_in_email_message(self) -> None:
        msg = EmailMessage(
            id="m1",
            gmail_message_id="m1",
            from_address="a@b.com",
            received_at=datetime.now(tz=UTC),
            to_addresses=[RecipientData(email="x@y.com", name="X")],
        )
        assert msg.to_addresses[0]["email"] == "x@y.com"


class TestAttachmentData:
    def test_construction(self) -> None:
        a = AttachmentData(
            filename="report.pdf",
            mime_type="application/pdf",
            size_bytes=2048,
            attachment_id="att_123",
        )
        assert a["filename"] == "report.pdf"
        assert a["mime_type"] == "application/pdf"
        assert a["size_bytes"] == 2048
        assert a["attachment_id"] == "att_123"


# ---------------------------------------------------------------------------
# DraftId
# ---------------------------------------------------------------------------


class TestDraftId:
    def test_construction(self) -> None:
        draft_id = DraftId("draft_abc123")
        assert draft_id == "draft_abc123"
        assert isinstance(draft_id, str)

    def test_empty_string(self) -> None:
        draft_id = DraftId("")
        assert draft_id == ""


# ---------------------------------------------------------------------------
# Other Pydantic models
# ---------------------------------------------------------------------------


class TestConnectionTestResult:
    def test_connected_true(self) -> None:
        r = ConnectionTestResult(
            connected=True,
            account="user@gmail.com",
            scopes=["gmail.readonly"],
            error=None,
        )
        assert r.connected is True
        assert r.error is None

    def test_connected_false_with_error(self) -> None:
        r = ConnectionTestResult(
            connected=False,
            error="connection refused",
        )
        assert r.connected is False
        assert r.error == "connection refused"
        assert r.account is None
        assert r.scopes == []


class TestConnectionStatus:
    def test_connected(self) -> None:
        s = ConnectionStatus(
            connected=True,
            account="user@gmail.com",
            scopes=["gmail.readonly"],
        )
        assert s.connected is True
        assert s.account == "user@gmail.com"


class TestEmailCredentials:
    def test_full_construction(self) -> None:
        c = EmailCredentials(
            client_id="cid",
            client_secret="csecret",
            token="tok",
            refresh_token="rtok",
            token_uri="https://oauth2.googleapis.com/token",
            scopes=["gmail.readonly"],
        )
        assert c.client_id == "cid"
        assert c.scopes == ["gmail.readonly"]

    def test_empty_fields_valid_at_schema_level(self) -> None:
        c = EmailCredentials(
            client_id="",
            client_secret="",
            token="",
            refresh_token="",
        )
        assert c.client_id == ""


class TestLabel:
    def test_construction(self) -> None:
        label = Label(id="INBOX", name="Inbox", type="system")
        assert label.id == "INBOX"
        assert label.name == "Inbox"
        assert label.type == "system"
