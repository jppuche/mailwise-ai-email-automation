"""Contract tests for the EmailAdapter ABC.

Uses a ``MockEmailAdapter`` that implements all 7 abstract methods.
Verifies that *any* correct implementation satisfies the contract:
correct return types, expected exceptions for invalid inputs,
``test_connection()`` never raises.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.adapters.email.base import EmailAdapter
from src.adapters.email.schemas import (
    ConnectionStatus,
    ConnectionTestResult,
    DraftId,
    EmailCredentials,
    EmailMessage,
    Label,
)

# ---------------------------------------------------------------------------
# MockEmailAdapter — minimal concrete implementation
# ---------------------------------------------------------------------------


class MockEmailAdapter(EmailAdapter):
    """Simplest valid implementation satisfying the ABC contract."""

    def connect(self, credentials: EmailCredentials) -> ConnectionStatus:
        if not credentials.client_id:
            raise ValueError("client_id must not be empty")
        return ConnectionStatus(connected=True, account="mock@example.com", scopes=[])

    def fetch_new_messages(self, since: datetime, limit: int) -> list[EmailMessage]:
        if since.tzinfo is None:
            raise ValueError("since must be a timezone-aware datetime")
        if not (1 <= limit <= 500):
            raise ValueError("limit must be between 1 and 500")
        return []

    def mark_as_processed(self, message_id: str) -> None:
        if not message_id:
            raise ValueError("message_id must not be empty")

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
    ) -> DraftId:
        if not to or "@" not in to:
            raise ValueError("to must be a valid email address")
        if not body:
            raise ValueError("body must not be empty")
        return DraftId("mock_draft_id")

    def get_labels(self) -> list[Label]:
        return [Label(id="INBOX", name="Inbox", type="system")]

    def apply_label(self, message_id: str, label_id: str) -> None:
        if not message_id:
            raise ValueError("message_id must not be empty")
        if not label_id:
            raise ValueError("label_id must not be empty")

    def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            connected=True,
            account="mock@example.com",
            scopes=[],
            error=None,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestABCSatisfiability:
    """Verify that the ABC can be instantiated and methods return correct types."""

    def test_can_instantiate(self) -> None:
        adapter = MockEmailAdapter()
        assert isinstance(adapter, EmailAdapter)

    def test_connect_returns_connection_status(self) -> None:
        adapter = MockEmailAdapter()
        creds = EmailCredentials(
            client_id="cid",
            client_secret="cs",
            token="tok",
            refresh_token="rtok",
        )
        result = adapter.connect(creds)
        assert isinstance(result, ConnectionStatus)
        assert result.connected is True

    def test_fetch_returns_list_of_email_message(self) -> None:
        adapter = MockEmailAdapter()
        result = adapter.fetch_new_messages(since=datetime.now(tz=UTC), limit=10)
        assert isinstance(result, list)

    def test_create_draft_returns_draft_id(self) -> None:
        adapter = MockEmailAdapter()
        result = adapter.create_draft(to="test@example.com", subject="S", body="B")
        assert isinstance(result, str)

    def test_get_labels_returns_list_of_label(self) -> None:
        adapter = MockEmailAdapter()
        result = adapter.get_labels()
        assert isinstance(result, list)
        assert all(isinstance(lbl, Label) for lbl in result)

    def test_test_connection_returns_result(self) -> None:
        adapter = MockEmailAdapter()
        result = adapter.test_connection()
        assert isinstance(result, ConnectionTestResult)
        assert hasattr(result, "connected")
        assert hasattr(result, "account")
        assert hasattr(result, "scopes")
        assert hasattr(result, "error")


class TestContractViolations:
    """Verify that contract violations produce the documented exceptions."""

    def test_connect_empty_client_id_raises(self) -> None:
        adapter = MockEmailAdapter()
        creds = EmailCredentials(
            client_id="",
            client_secret="cs",
            token="tok",
            refresh_token="rtok",
        )
        with pytest.raises(ValueError, match="client_id"):
            adapter.connect(creds)

    def test_fetch_naive_since_raises(self) -> None:
        adapter = MockEmailAdapter()
        naive = datetime(2025, 1, 1)  # noqa: DTZ001
        with pytest.raises(ValueError, match="timezone-aware"):
            adapter.fetch_new_messages(since=naive, limit=10)

    def test_fetch_limit_zero_raises(self) -> None:
        adapter = MockEmailAdapter()
        with pytest.raises(ValueError, match="limit"):
            adapter.fetch_new_messages(since=datetime.now(tz=UTC), limit=0)

    def test_fetch_limit_over_500_raises(self) -> None:
        adapter = MockEmailAdapter()
        with pytest.raises(ValueError, match="limit"):
            adapter.fetch_new_messages(since=datetime.now(tz=UTC), limit=501)

    def test_mark_empty_message_id_raises(self) -> None:
        adapter = MockEmailAdapter()
        with pytest.raises(ValueError, match="message_id"):
            adapter.mark_as_processed("")

    def test_create_draft_invalid_to_raises(self) -> None:
        adapter = MockEmailAdapter()
        with pytest.raises(ValueError, match="email"):
            adapter.create_draft(to="not-an-email", subject="S", body="B")

    def test_create_draft_empty_body_raises(self) -> None:
        adapter = MockEmailAdapter()
        with pytest.raises(ValueError, match="body"):
            adapter.create_draft(to="a@b.com", subject="S", body="")

    def test_apply_label_empty_message_id_raises(self) -> None:
        adapter = MockEmailAdapter()
        with pytest.raises(ValueError, match="message_id"):
            adapter.apply_label("", "LABEL_1")

    def test_apply_label_empty_label_id_raises(self) -> None:
        adapter = MockEmailAdapter()
        with pytest.raises(ValueError, match="label_id"):
            adapter.apply_label("msg1", "")
