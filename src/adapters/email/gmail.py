"""GmailAdapter — concrete EmailAdapter for the Gmail API.

contract-docstrings:
  Invariants: OAuth2 credentials loaded via ``connect()``. Gmail API service
    built with ``googleapiclient.discovery.build``.
  Guarantees: All returned values are typed schemas — raw Gmail dicts stay
    inside this module. Deduplication is the caller's responsibility.
  Errors raised: Typed ``EmailAdapterError`` subclasses (see exceptions.py).
  Errors silenced: ``test_connection()`` silences all errors.
    ``fetch_new_messages()`` silences per-message parse failures.
  External state: Gmail API via google-api-python-client.

try-except D7: Every Gmail API call uses structured try/except for
  ``HttpError`` (by status code) and ``RefreshError``.
try-except D8: Argument validation uses conditionals, not try/except.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from email.mime.text import MIMEText
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

import structlog
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.adapters.email.base import EmailAdapter
from src.adapters.email.exceptions import (
    AuthError,
    DraftCreationError,
    EmailAdapterError,
    EmailConnectionError,
    FetchError,
    LabelError,
    RateLimitError,
)
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
from src.core.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Private helpers — parsing Gmail API responses
# ---------------------------------------------------------------------------


def _get_header(headers: list[dict[str, str]], name: str) -> str:
    """Extract a single header value by name (case-insensitive)."""
    name_lower = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name_lower:
            return h.get("value", "")
    return ""


def _parse_address(raw: str) -> RecipientData:
    """Parse an RFC 5322 address into ``RecipientData``."""
    display_name, email = parseaddr(raw)
    return RecipientData(
        name=display_name if display_name else None,
        email=email or raw,
    )


def _parse_address_list(raw: str) -> list[RecipientData]:
    """Parse a comma-separated address header into a list."""
    if not raw:
        return []
    return [_parse_address(addr.strip()) for addr in raw.split(",") if addr.strip()]


def _decode_body_data(data: str) -> str:
    """Decode base64url-encoded body data from Gmail API."""
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")


def _extract_body(
    payload: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Extract plain and HTML body from a Gmail message payload.

    Walks the MIME structure, preferring ``text/plain`` and ``text/html``
    parts. Returns ``(body_plain, body_html)``.
    """
    body_plain: str | None = None
    body_html: str | None = None

    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")

    if mime_type == "text/plain" and body_data:
        body_plain = _decode_body_data(body_data)
    elif mime_type == "text/html" and body_data:
        body_html = _decode_body_data(body_data)

    for part in payload.get("parts", []):
        part_plain, part_html = _extract_body(part)
        if part_plain and body_plain is None:
            body_plain = part_plain
        if part_html and body_html is None:
            body_html = part_html

    return body_plain, body_html


def _extract_attachments(payload: dict[str, Any]) -> list[AttachmentData]:
    """Extract attachment metadata from a Gmail message payload."""
    attachments: list[AttachmentData] = []
    for part in payload.get("parts", []):
        filename = part.get("filename", "")
        if filename:
            body = part.get("body", {})
            attachments.append(
                AttachmentData(
                    filename=filename,
                    mime_type=part.get("mimeType", "application/octet-stream"),
                    size_bytes=body.get("size", 0),
                    attachment_id=body.get("attachmentId", ""),
                )
            )
        # Recurse into nested multipart
        attachments.extend(_extract_attachments(part))
    return attachments


def _parse_date(raw: str) -> datetime:
    """Parse an RFC 2822 date string into a timezone-aware datetime."""
    if not raw:
        return datetime.now(tz=UTC)
    dt = parsedate_to_datetime(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _parse_message(raw_msg: dict[str, Any]) -> EmailMessage:
    """Convert a raw Gmail API message dict into an ``EmailMessage``.

    This is the sole point where untyped Gmail dicts are transformed into
    typed adapter schemas.  Validation errors propagate as ``ValueError``
    or ``KeyError`` — the caller (``fetch_new_messages``) isolates each
    call in a per-message try/except.
    """
    payload = raw_msg["payload"]
    headers = payload.get("headers", [])

    from_raw = _get_header(headers, "From")
    from_data = _parse_address(from_raw)

    to_raw = _get_header(headers, "To")
    cc_raw = _get_header(headers, "Cc")

    body_plain, body_html = _extract_body(payload)

    raw_headers: dict[str, str] = {
        h["name"]: h["value"] for h in headers if "name" in h and "value" in h
    }

    return EmailMessage(
        id=raw_msg["id"],
        gmail_message_id=raw_msg["id"],
        thread_id=raw_msg.get("threadId"),
        subject=_get_header(headers, "Subject"),
        from_address=from_data["email"],
        to_addresses=_parse_address_list(to_raw),
        cc_addresses=_parse_address_list(cc_raw),
        body_plain=body_plain,
        body_html=body_html,
        snippet=raw_msg.get("snippet"),
        received_at=_parse_date(_get_header(headers, "Date")),
        attachments=_extract_attachments(payload),
        raw_headers=raw_headers,
        provider_labels=raw_msg.get("labelIds", []),
    )


# ---------------------------------------------------------------------------
# GmailAdapter
# ---------------------------------------------------------------------------


class GmailAdapter(EmailAdapter):
    """Gmail API adapter using ``google-api-python-client``.

    The adapter manages OAuth2 credentials, token refresh, API pagination,
    and MIME parsing. All raw Gmail dicts are converted to typed schemas
    before crossing the adapter boundary.
    """

    def __init__(self) -> None:
        self._credentials: Credentials | None = None
        self._service: Any | None = None  # googleapiclient Resource (untyped)

    # -- Private helpers ---------------------------------------------------

    def _ensure_connected(self) -> None:
        """Validate that the adapter has been connected."""
        if self._service is None or self._credentials is None:
            raise EmailAdapterError("Adapter is not connected — call connect() first")

    def _refresh_credentials(self) -> None:
        """Refresh OAuth2 access token if expired."""
        if (
            self._credentials is not None
            and self._credentials.expired
            and self._credentials.refresh_token
        ):
            try:
                self._credentials.refresh(Request())
            except RefreshError as exc:
                raise AuthError("OAuth2 token refresh failed", original_error=exc) from exc

    def _map_http_error(
        self,
        exc: HttpError,
        context_error: type[EmailAdapterError] = FetchError,
    ) -> EmailAdapterError:
        """Map an ``HttpError`` to the appropriate adapter exception."""
        code: int = exc.status_code
        reason = str(exc)
        if code == 401:
            return AuthError(f"Gmail 401: {reason}", original_error=exc)
        if code == 429:
            return RateLimitError("Gmail rate limit exceeded", original_error=exc)
        if code >= 500:
            return EmailConnectionError(f"Gmail server error {code}", original_error=exc)
        return context_error(f"Gmail API error {code}: {reason}", original_error=exc)

    # -- Public interface (EmailAdapter ABC) --------------------------------

    def connect(self, credentials: EmailCredentials) -> ConnectionStatus:
        if not credentials.client_id:
            raise ValueError("credentials.client_id must not be empty")
        if not credentials.client_secret:
            raise ValueError("credentials.client_secret must not be empty")
        if not credentials.token:
            raise ValueError("credentials.token must not be empty")
        if not credentials.refresh_token:
            raise ValueError("credentials.refresh_token must not be empty")

        google_creds = Credentials(  # type: ignore[no-untyped-call]
            token=credentials.token,
            refresh_token=credentials.refresh_token,
            token_uri=credentials.token_uri,
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
            scopes=credentials.scopes,
        )

        try:
            service = build("gmail", "v1", credentials=google_creds)
            profile = service.users().getProfile(userId="me").execute()
        except HttpError as exc:
            raise self._map_http_error(exc) from exc
        except RefreshError as exc:
            raise AuthError(
                "OAuth2 token refresh failed during connect",
                original_error=exc,
            ) from exc

        self._credentials = google_creds
        self._service = service

        return ConnectionStatus(
            connected=True,
            account=profile.get("emailAddress"),
            scopes=list(credentials.scopes),
        )

    def fetch_new_messages(self, since: datetime, limit: int) -> list[EmailMessage]:
        if since.tzinfo is None:
            raise ValueError("since must be a timezone-aware datetime")
        if not (1 <= limit <= 500):
            raise ValueError("limit must be between 1 and 500")
        self._ensure_connected()
        assert self._service is not None  # narrowed by _ensure_connected
        self._refresh_credentials()

        settings = get_settings()
        epoch = int(since.timestamp())
        query = f"after:{epoch}"

        # Phase 1: collect message IDs via paginated list
        message_ids: list[str] = []
        page_token: str | None = None

        try:
            while len(message_ids) < limit:
                max_results = min(settings.gmail_max_results, limit - len(message_ids))
                request_kwargs: dict[str, Any] = {
                    "userId": "me",
                    "q": query,
                    "maxResults": max_results,
                }
                if page_token:
                    request_kwargs["pageToken"] = page_token

                response = self._service.users().messages().list(**request_kwargs).execute()

                for msg in response.get("messages", []):
                    if len(message_ids) >= limit:
                        break
                    message_ids.append(msg["id"])

                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        except HttpError as exc:
            raise self._map_http_error(exc) from exc

        # Phase 2: fetch full message for each ID
        messages: list[EmailMessage] = []
        for msg_id in message_ids:
            try:
                raw = (
                    self._service.users()
                    .messages()
                    .get(userId="me", id=msg_id, format="full")
                    .execute()
                )
                messages.append(_parse_message(raw))
            except HttpError as exc:
                raise self._map_http_error(exc) from exc
            except (KeyError, ValueError, TypeError) as exc:
                # Per-message parse failure: log and continue
                logger.warning(
                    "skipping_unparseable_message",
                    message_id=msg_id,
                    error=str(exc),
                    exc_info=True,
                )
                continue

        return messages

    def mark_as_processed(self, message_id: str) -> None:
        if not message_id:
            raise ValueError("message_id must not be empty")
        self._ensure_connected()
        assert self._service is not None  # narrowed by _ensure_connected
        self._refresh_credentials()

        try:
            self._service.users().messages().modify(
                userId="me",
                id=message_id,
                body={
                    "addLabelIds": ["PROCESSED"],
                    "removeLabelIds": ["UNREAD"],
                },
            ).execute()
        except HttpError as exc:
            raise self._map_http_error(exc) from exc

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
    ) -> DraftId:
        if not to or "@" not in to:
            raise ValueError(f"to must be a valid email address, got: {to!r}")
        if not body:
            raise ValueError("body must not be empty")
        self._ensure_connected()
        assert self._service is not None  # narrowed by _ensure_connected
        self._refresh_credentials()

        mime_message = MIMEText(body, "plain", "utf-8")
        mime_message["to"] = to
        mime_message["subject"] = subject
        if in_reply_to is not None:
            mime_message["In-Reply-To"] = in_reply_to
            mime_message["References"] = in_reply_to

        raw = base64.urlsafe_b64encode(mime_message.as_bytes()).decode("ascii")

        try:
            result = (
                self._service.users()
                .drafts()
                .create(userId="me", body={"message": {"raw": raw}})
                .execute()
            )
        except HttpError as exc:
            raise self._map_http_error(exc, context_error=DraftCreationError) from exc

        return DraftId(result["id"])

    def get_labels(self) -> list[Label]:
        self._ensure_connected()
        assert self._service is not None  # narrowed by _ensure_connected
        self._refresh_credentials()

        try:
            response = self._service.users().labels().list(userId="me").execute()
        except HttpError as exc:
            raise self._map_http_error(exc, context_error=LabelError) from exc

        labels: list[Label] = []
        for item in response.get("labels", []):
            labels.append(
                Label(
                    id=item["id"],
                    name=item["name"],
                    type=item.get("type", "user").lower(),
                )
            )
        return labels

    def apply_label(self, message_id: str, label_id: str) -> None:
        if not message_id:
            raise ValueError("message_id must not be empty")
        if not label_id:
            raise ValueError("label_id must not be empty")
        self._ensure_connected()
        assert self._service is not None  # narrowed by _ensure_connected
        self._refresh_credentials()

        try:
            self._service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"addLabelIds": [label_id]},
            ).execute()
        except HttpError as exc:
            raise self._map_http_error(exc, context_error=LabelError) from exc

    def test_connection(self) -> ConnectionTestResult:
        if self._service is None or self._credentials is None:
            return ConnectionTestResult(
                connected=False,
                account=None,
                scopes=[],
                error="Adapter not connected — credentials not loaded",
            )
        try:
            profile = self._service.users().getProfile(userId="me").execute()
            return ConnectionTestResult(
                connected=True,
                account=profile.get("emailAddress"),
                scopes=list(self._credentials.scopes or []),
                error=None,
            )
        except Exception as exc:  # noqa: BLE001 — health-check silences ALL errors
            return ConnectionTestResult(
                connected=False,
                account=None,
                scopes=[],
                error=str(exc),
            )
