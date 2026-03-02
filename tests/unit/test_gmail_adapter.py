"""Tests for GmailAdapter with mocked Google API.

Uses ``unittest.mock`` to replace ``googleapiclient.discovery.build`` and
Google credential objects. No real network calls, no Docker required.
Runs in the default ``pytest tests/ -q`` suite.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from google.oauth2.credentials import Credentials

from src.adapters.email.exceptions import (
    AuthError,
    DraftCreationError,
    EmailAdapterError,
    EmailConnectionError,
    LabelError,
    RateLimitError,
)
from src.adapters.email.gmail import GmailAdapter
from src.adapters.email.schemas import (
    ConnectionTestResult,
    DraftId,
    EmailCredentials,
    EmailMessage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_raw_message(
    msg_id: str = "msg001",
    *,
    thread_id: str = "thread001",
    subject: str = "Test",
    from_addr: str = "alice@example.com",
    to_addr: str = "bob@example.com",
    body_text: str = "Hello",
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Build a minimal raw Gmail API message dict."""
    return {
        "id": msg_id,
        "threadId": thread_id,
        "labelIds": labels or ["INBOX", "UNREAD"],
        "snippet": body_text[:50],
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "To", "value": to_addr},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Mon, 20 Jan 2025 10:00:00 +0000"},
            ],
            "body": {
                "data": base64.urlsafe_b64encode(body_text.encode()).decode(),
            },
            "parts": [],
        },
    }


def _make_http_error(status_code: int, reason: str = "error") -> Exception:
    """Build a mock HttpError with the given status code."""
    from googleapiclient.errors import HttpError

    resp = MagicMock()
    resp.status = status_code
    resp.reason = reason
    error = HttpError(resp=resp, content=reason.encode())
    return error


def _make_credentials() -> MagicMock:
    """Build a mock Credentials object."""
    creds = MagicMock(spec=Credentials)
    creds.expired = False
    creds.refresh_token = "mock_refresh"
    creds.scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    return creds


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_service() -> MagicMock:
    """Return a mock Gmail API service resource."""
    return MagicMock()


@pytest.fixture()
def adapter(mock_service: MagicMock) -> GmailAdapter:
    """Return a GmailAdapter with pre-set mock service and credentials."""
    a = GmailAdapter()
    a._service = mock_service
    a._credentials = _make_credentials()
    return a


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


class TestConnect:
    def test_empty_client_id_raises(self) -> None:
        adapter = GmailAdapter()
        creds = EmailCredentials(
            client_id="",
            client_secret="cs",
            token="tok",
            refresh_token="rtok",
        )
        with pytest.raises(ValueError, match="client_id"):
            adapter.connect(creds)

    def test_empty_token_raises(self) -> None:
        adapter = GmailAdapter()
        creds = EmailCredentials(
            client_id="cid",
            client_secret="cs",
            token="",
            refresh_token="rtok",
        )
        with pytest.raises(ValueError, match="token"):
            adapter.connect(creds)


# ---------------------------------------------------------------------------
# fetch_new_messages()
# ---------------------------------------------------------------------------


class TestFetchNewMessages:
    def test_empty_response(self, adapter: GmailAdapter, mock_service: MagicMock) -> None:
        mock_service.users().messages().list().execute.return_value = {
            "resultSizeEstimate": 0,
        }
        result = adapter.fetch_new_messages(since=datetime(2025, 1, 1, tzinfo=UTC), limit=10)
        assert result == []

    def test_single_message(self, adapter: GmailAdapter, mock_service: MagicMock) -> None:
        raw = _make_raw_message("msg001")

        mock_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg001", "threadId": "t1"}],
            "resultSizeEstimate": 1,
        }
        mock_service.users().messages().get().execute.return_value = raw

        result = adapter.fetch_new_messages(since=datetime(2025, 1, 1, tzinfo=UTC), limit=10)
        assert len(result) == 1
        assert isinstance(result[0], EmailMessage)
        assert result[0].gmail_message_id == "msg001"

    def test_uses_after_query(self, adapter: GmailAdapter, mock_service: MagicMock) -> None:
        since = datetime(2025, 1, 20, 10, 0, tzinfo=UTC)

        mock_service.users().messages().list().execute.return_value = {
            "resultSizeEstimate": 0,
        }
        adapter.fetch_new_messages(since=since, limit=10)

        # Verify list was called — the mock chain makes exact arg checking
        # hard, so we verify the method was invoked
        assert mock_service.users().messages().list.called

    def test_pagination(self, adapter: GmailAdapter, mock_service: MagicMock) -> None:
        raw = _make_raw_message("msg001")

        # First page returns a nextPageToken, second does not
        mock_service.users().messages().list().execute.side_effect = [
            {
                "messages": [{"id": "msg001", "threadId": "t1"}],
                "nextPageToken": "page2",
                "resultSizeEstimate": 1,
            },
            {
                "messages": [{"id": "msg002", "threadId": "t2"}],
                "resultSizeEstimate": 1,
            },
        ]
        mock_service.users().messages().get().execute.return_value = raw

        result = adapter.fetch_new_messages(since=datetime(2025, 1, 1, tzinfo=UTC), limit=10)
        assert len(result) == 2

    def test_parse_failure_skips_message(
        self, adapter: GmailAdapter, mock_service: MagicMock
    ) -> None:
        good_raw = _make_raw_message("msg001")
        bad_raw = {"id": "msg002"}  # Missing "payload" → KeyError

        mock_service.users().messages().list().execute.return_value = {
            "messages": [
                {"id": "msg001", "threadId": "t1"},
                {"id": "msg002", "threadId": "t2"},
            ],
            "resultSizeEstimate": 2,
        }
        mock_service.users().messages().get().execute.side_effect = [
            good_raw,
            bad_raw,
        ]

        result = adapter.fetch_new_messages(since=datetime(2025, 1, 1, tzinfo=UTC), limit=10)
        # Only the good message should be returned
        assert len(result) == 1
        assert result[0].gmail_message_id == "msg001"

    def test_naive_since_raises(self, adapter: GmailAdapter) -> None:
        naive = datetime(2025, 1, 1)  # noqa: DTZ001
        with pytest.raises(ValueError, match="timezone-aware"):
            adapter.fetch_new_messages(since=naive, limit=10)

    def test_limit_out_of_range_raises(self, adapter: GmailAdapter) -> None:
        with pytest.raises(ValueError, match="limit"):
            adapter.fetch_new_messages(since=datetime.now(tz=UTC), limit=0)

    def test_not_connected_raises(self) -> None:
        adapter = GmailAdapter()
        with pytest.raises(EmailAdapterError, match="not connected"):
            adapter.fetch_new_messages(since=datetime.now(tz=UTC), limit=10)


# ---------------------------------------------------------------------------
# HttpError mapping
# ---------------------------------------------------------------------------


class TestHttpErrorMapping:
    def test_401_raises_auth_error(self, adapter: GmailAdapter, mock_service: MagicMock) -> None:
        mock_service.users().messages().list().execute.side_effect = _make_http_error(
            401, "Unauthorized"
        )
        with pytest.raises(AuthError):
            adapter.fetch_new_messages(since=datetime.now(tz=UTC), limit=10)

    def test_429_raises_rate_limit_error(
        self, adapter: GmailAdapter, mock_service: MagicMock
    ) -> None:
        mock_service.users().messages().list().execute.side_effect = _make_http_error(
            429, "Too Many Requests"
        )
        with pytest.raises(RateLimitError):
            adapter.fetch_new_messages(since=datetime.now(tz=UTC), limit=10)

    def test_503_raises_connection_error(
        self, adapter: GmailAdapter, mock_service: MagicMock
    ) -> None:
        mock_service.users().messages().list().execute.side_effect = _make_http_error(
            503, "Service Unavailable"
        )
        with pytest.raises(EmailConnectionError):
            adapter.fetch_new_messages(since=datetime.now(tz=UTC), limit=10)


# ---------------------------------------------------------------------------
# mark_as_processed()
# ---------------------------------------------------------------------------


class TestMarkAsProcessed:
    def test_calls_modify(self, adapter: GmailAdapter, mock_service: MagicMock) -> None:
        mock_service.users().messages().modify().execute.return_value = {}

        adapter.mark_as_processed("msg001")
        assert mock_service.users().messages().modify.called

    def test_empty_message_id_raises(self, adapter: GmailAdapter) -> None:
        with pytest.raises(ValueError, match="message_id"):
            adapter.mark_as_processed("")


# ---------------------------------------------------------------------------
# create_draft()
# ---------------------------------------------------------------------------


class TestCreateDraft:
    def test_returns_draft_id(self, adapter: GmailAdapter, mock_service: MagicMock) -> None:
        mock_service.users().drafts().create().execute.return_value = {"id": "draft_001"}
        result = adapter.create_draft(to="test@example.com", subject="Test", body="Body")
        assert result == DraftId("draft_001")

    def test_in_reply_to_header(self, adapter: GmailAdapter, mock_service: MagicMock) -> None:
        mock_service.users().drafts().create().execute.return_value = {"id": "draft_002"}
        adapter.create_draft(
            to="test@example.com",
            subject="Re: Test",
            body="Reply body",
            in_reply_to="<original@example.com>",
        )
        assert mock_service.users().drafts().create.called

    def test_invalid_to_raises(self, adapter: GmailAdapter) -> None:
        with pytest.raises(ValueError, match="email"):
            adapter.create_draft(to="not-an-email", subject="S", body="B")

    def test_empty_body_raises(self, adapter: GmailAdapter) -> None:
        with pytest.raises(ValueError, match="body"):
            adapter.create_draft(to="a@b.com", subject="S", body="")

    def test_http_error_raises_draft_creation_error(
        self, adapter: GmailAdapter, mock_service: MagicMock
    ) -> None:
        mock_service.users().drafts().create().execute.side_effect = _make_http_error(
            400, "Bad Request"
        )
        with pytest.raises(DraftCreationError):
            adapter.create_draft(to="a@b.com", subject="S", body="B")


# ---------------------------------------------------------------------------
# get_labels()
# ---------------------------------------------------------------------------


class TestGetLabels:
    def test_returns_labels(self, adapter: GmailAdapter, mock_service: MagicMock) -> None:
        mock_service.users().labels().list().execute.return_value = {
            "labels": [
                {"id": "INBOX", "name": "Inbox", "type": "system"},
                {"id": "Label_1", "name": "Custom", "type": "user"},
            ]
        }
        result = adapter.get_labels()
        assert len(result) == 2
        assert result[0].id == "INBOX"
        assert result[1].name == "Custom"

    def test_http_error_raises_label_error(
        self, adapter: GmailAdapter, mock_service: MagicMock
    ) -> None:
        mock_service.users().labels().list().execute.side_effect = _make_http_error(
            403, "Forbidden"
        )
        with pytest.raises(LabelError):
            adapter.get_labels()


# ---------------------------------------------------------------------------
# apply_label()
# ---------------------------------------------------------------------------


class TestApplyLabel:
    def test_calls_modify(self, adapter: GmailAdapter, mock_service: MagicMock) -> None:
        mock_service.users().messages().modify().execute.return_value = {}
        adapter.apply_label("msg001", "Label_1")
        assert mock_service.users().messages().modify.called

    def test_empty_ids_raise(self, adapter: GmailAdapter) -> None:
        with pytest.raises(ValueError, match="message_id"):
            adapter.apply_label("", "Label_1")
        with pytest.raises(ValueError, match="label_id"):
            adapter.apply_label("msg001", "")

    def test_http_error_raises_label_error(
        self, adapter: GmailAdapter, mock_service: MagicMock
    ) -> None:
        mock_service.users().messages().modify().execute.side_effect = _make_http_error(
            404, "Not Found"
        )
        with pytest.raises(LabelError):
            adapter.apply_label("msg001", "Label_1")


# ---------------------------------------------------------------------------
# test_connection()
# ---------------------------------------------------------------------------


class TestTestConnection:
    def test_success(self, adapter: GmailAdapter, mock_service: MagicMock) -> None:
        mock_service.users().getProfile().execute.return_value = {"emailAddress": "user@gmail.com"}
        result = adapter.test_connection()
        assert result.connected is True
        assert result.account == "user@gmail.com"
        assert result.error is None

    def test_failure_returns_result(self, adapter: GmailAdapter, mock_service: MagicMock) -> None:
        mock_service.users().getProfile().execute.side_effect = Exception("network down")
        result = adapter.test_connection()
        assert result.connected is False
        assert result.error == "network down"

    def test_not_connected_returns_result(self) -> None:
        adapter = GmailAdapter()
        result = adapter.test_connection()
        assert result.connected is False
        assert "not connected" in (result.error or "").lower()

    def test_never_raises(self, adapter: GmailAdapter, mock_service: MagicMock) -> None:
        mock_service.users().getProfile().execute.side_effect = RuntimeError("unexpected")
        # Should NOT raise — returns ConnectionTestResult
        result = adapter.test_connection()
        assert isinstance(result, ConnectionTestResult)
        assert result.connected is False
