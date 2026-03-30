"""Unit tests for GET/POST /api/v1/drafts/ endpoints.

Pattern:
  - dependency_overrides for auth, DB, and require_draft_access
  - require_draft_access bypassed with a pre-built mock Draft
  - No real DB or Redis
  - Tests document observable HTTP behaviour, not router internals

Tests use assertions (conditionals) only — no try/except in test bodies.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.api.deps import require_draft_access
from src.api.main import app
from src.core.exceptions import AuthorizationError, NotFoundError
from src.models.draft import Draft, DraftStatus
from src.models.email import Email
from src.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scalar_result(obj: object) -> MagicMock:
    """Return a mock execute-result whose scalar_one_or_none() returns *obj*."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    return result


def _scalars_all_result(items: list[object]) -> MagicMock:
    """Return a mock execute-result whose scalars().all() returns *items*."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    result.scalars.return_value = scalars_mock
    return result


def _scalar_one_result(value: object) -> MagicMock:
    """Return a mock execute-result whose scalar_one() returns *value*."""
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def _make_mock_draft(
    draft_id: uuid.UUID | None = None,
    email_id: uuid.UUID | None = None,
    reviewer_id: uuid.UUID | None = None,
    status: DraftStatus = DraftStatus.PENDING,
) -> MagicMock:
    """Build a MagicMock Draft ORM object."""
    draft = MagicMock(spec=Draft)
    draft.id = draft_id or uuid.uuid4()
    draft.email_id = email_id or uuid.uuid4()
    draft.content = "Draft reply content"
    draft.status = status
    draft.reviewer_id = reviewer_id
    draft.reviewed_at = None
    draft.pushed_to_provider = False
    draft.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    draft.updated_at = datetime(2024, 1, 1, tzinfo=UTC)
    return draft


def _make_mock_email(email_id: uuid.UUID | None = None) -> MagicMock:
    """Build a MagicMock Email ORM object."""
    email = MagicMock(spec=Email)
    email.id = email_id or uuid.uuid4()
    email.subject = "Test Email Subject"
    email.sender_email = "sender@example.com"
    email.sender_name = "Test Sender"
    email.snippet = "This is a test snippet"
    email.date = datetime(2024, 1, 1, tzinfo=UTC)
    return email


# ---------------------------------------------------------------------------
# TestListDrafts
# ---------------------------------------------------------------------------


class TestListDrafts:
    """GET /api/v1/drafts/ — paginated list (role-scoped)."""

    @pytest.mark.asyncio
    async def test_admin_sees_all_drafts_gets_200(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
        admin_user: MagicMock,
    ) -> None:
        """Admin gets a 200 response with paginated draft list."""
        draft = _make_mock_draft()
        email = _make_mock_email(email_id=draft.email_id)

        # execute() is called 3 times: count, paginated drafts, email lookup
        mock_db.execute.side_effect = [
            _scalar_one_result(1),  # COUNT
            _scalars_all_result([draft]),  # paginated drafts
            _scalars_all_result([email]),  # email map
        ]

        response = await admin_client.get("/api/v1/drafts/")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["email_subject"] == "Test Email Subject"

    @pytest.mark.asyncio
    async def test_reviewer_sees_only_own_drafts(
        self,
        reviewer_client: AsyncClient,
        mock_db: AsyncMock,
        reviewer_user: MagicMock,
    ) -> None:
        """Reviewer gets 200; the router scopes the query to reviewer_id."""
        draft = _make_mock_draft(reviewer_id=reviewer_user.id)
        email = _make_mock_email(email_id=draft.email_id)

        mock_db.execute.side_effect = [
            _scalar_one_result(1),
            _scalars_all_result([draft]),
            _scalars_all_result([email]),
        ]

        response = await reviewer_client.get("/api/v1/drafts/")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["reviewer_id"] == str(reviewer_user.id)

    @pytest.mark.asyncio
    async def test_unauthenticated_gets_401(self, unauthenticated_client: AsyncClient) -> None:
        """Missing token returns 401."""
        response = await unauthenticated_client.get("/api/v1/drafts/")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_list_returns_correct_pagination(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Empty result set returns total=0, pages=0, items=[]."""
        mock_db.execute.side_effect = [
            _scalar_one_result(0),  # COUNT
            _scalars_all_result([]),  # no drafts
            # no email query since email_ids is empty
        ]

        response = await admin_client.get("/api/v1/drafts/")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 0
        assert body["pages"] == 0
        assert body["items"] == []


# ---------------------------------------------------------------------------
# TestGetDraft
# ---------------------------------------------------------------------------


class TestGetDraft:
    """GET /api/v1/drafts/{draft_id} — draft detail with email context."""

    @pytest.mark.asyncio
    async def test_admin_gets_draft_with_email_context(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
        admin_user: MagicMock,
    ) -> None:
        """Admin fetches a draft and sees email context; no classification."""
        draft_id = uuid.uuid4()
        email_id = uuid.uuid4()
        draft = _make_mock_draft(draft_id=draft_id, email_id=email_id)
        email = _make_mock_email(email_id=email_id)

        # Override require_draft_access to return our mock draft directly
        app.dependency_overrides[require_draft_access] = lambda: draft

        # DB execute calls in get_draft: email query, classification query
        mock_db.execute.side_effect = [
            _scalar_result(email),  # email lookup
            _scalar_result(None),  # classification (none)
        ]

        try:
            response = await admin_client.get(f"/api/v1/drafts/{draft_id}")
        finally:
            app.dependency_overrides.pop(require_draft_access, None)

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(draft_id)
        assert body["email"]["subject"] == "Test Email Subject"
        assert body["email"]["classification"] is None

    @pytest.mark.asyncio
    async def test_missing_draft_gets_404(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """require_draft_access raises NotFoundError for unknown draft ID."""
        draft_id = uuid.uuid4()

        # Raise NotFoundError from the dependency — simulates missing draft
        app.dependency_overrides[require_draft_access] = lambda: (_ for _ in ()).throw(
            NotFoundError(f"Draft {draft_id} not found")
        )

        try:
            response = await admin_client.get(f"/api/v1/drafts/{draft_id}")
        finally:
            app.dependency_overrides.pop(require_draft_access, None)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_reviewer_cannot_access_other_users_draft(
        self,
        reviewer_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """require_draft_access raises AuthorizationError for unowned draft."""
        draft_id = uuid.uuid4()

        app.dependency_overrides[require_draft_access] = lambda: (_ for _ in ()).throw(
            AuthorizationError("Access to this draft is not allowed")
        )

        try:
            response = await reviewer_client.get(f"/api/v1/drafts/{draft_id}")
        finally:
            app.dependency_overrides.pop(require_draft_access, None)

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# TestApproveDraft
# ---------------------------------------------------------------------------


class TestApproveDraft:
    """POST /api/v1/drafts/{draft_id}/approve — approve pending draft."""

    @pytest.mark.asyncio
    async def test_pending_draft_approved_gets_200(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
        admin_user: MagicMock,
    ) -> None:
        """Approving a PENDING draft returns 200 with gmail_draft_id=None."""
        draft_id = uuid.uuid4()
        draft = _make_mock_draft(draft_id=draft_id, status=DraftStatus.PENDING)

        app.dependency_overrides[require_draft_access] = lambda: draft

        try:
            response = await admin_client.post(
                f"/api/v1/drafts/{draft_id}/approve", json={"push_to_gmail": True}
            )
        finally:
            app.dependency_overrides.pop(require_draft_access, None)

        assert response.status_code == 200
        body = response.json()
        assert body["approved"] is True
        assert body["gmail_draft_id"] is None
        assert body["draft_id"] == str(draft_id)

    @pytest.mark.asyncio
    async def test_non_pending_draft_approve_gets_409(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Approving an already-APPROVED draft returns 409 Conflict."""
        draft_id = uuid.uuid4()
        draft = _make_mock_draft(draft_id=draft_id, status=DraftStatus.APPROVED)

        app.dependency_overrides[require_draft_access] = lambda: draft

        try:
            response = await admin_client.post(
                f"/api/v1/drafts/{draft_id}/approve", json={"push_to_gmail": True}
            )
        finally:
            app.dependency_overrides.pop(require_draft_access, None)

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_reviewer_can_approve_own_draft(
        self,
        reviewer_client: AsyncClient,
        mock_db: AsyncMock,
        reviewer_user: MagicMock,
    ) -> None:
        """Reviewer can approve a draft assigned to them."""
        draft_id = uuid.uuid4()
        draft = _make_mock_draft(
            draft_id=draft_id,
            reviewer_id=reviewer_user.id,
            status=DraftStatus.PENDING,
        )

        app.dependency_overrides[require_draft_access] = lambda: draft

        try:
            response = await reviewer_client.post(
                f"/api/v1/drafts/{draft_id}/approve", json={"push_to_gmail": False}
            )
        finally:
            app.dependency_overrides.pop(require_draft_access, None)

        assert response.status_code == 200
        body = response.json()
        assert body["approved"] is True

    @pytest.mark.asyncio
    async def test_unauthenticated_approve_gets_401(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """Missing token returns 401 on approve endpoint."""
        response = await unauthenticated_client.post(
            f"/api/v1/drafts/{uuid.uuid4()}/approve", json={"push_to_gmail": True}
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# TestRejectDraft
# ---------------------------------------------------------------------------


class TestRejectDraft:
    """POST /api/v1/drafts/{draft_id}/reject — reject pending draft (204)."""

    @pytest.mark.asyncio
    async def test_pending_draft_rejected_gets_204(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Rejecting a PENDING draft returns 204 No Content."""
        draft_id = uuid.uuid4()
        draft = _make_mock_draft(draft_id=draft_id, status=DraftStatus.PENDING)

        app.dependency_overrides[require_draft_access] = lambda: draft

        try:
            response = await admin_client.post(
                f"/api/v1/drafts/{draft_id}/reject", json={"reason": "Not acceptable"}
            )
        finally:
            app.dependency_overrides.pop(require_draft_access, None)

        assert response.status_code == 204
        assert response.content == b""

    @pytest.mark.asyncio
    async def test_non_pending_draft_reject_gets_409(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Rejecting an already-REJECTED draft returns 409 Conflict."""
        draft_id = uuid.uuid4()
        draft = _make_mock_draft(draft_id=draft_id, status=DraftStatus.REJECTED)

        app.dependency_overrides[require_draft_access] = lambda: draft

        try:
            response = await admin_client.post(
                f"/api/v1/drafts/{draft_id}/reject", json={"reason": "Already rejected"}
            )
        finally:
            app.dependency_overrides.pop(require_draft_access, None)

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_unauthenticated_reject_gets_401(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """Missing token returns 401 on reject endpoint."""
        response = await unauthenticated_client.post(
            f"/api/v1/drafts/{uuid.uuid4()}/reject", json={"reason": "No auth"}
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# TestReassignDraft
# ---------------------------------------------------------------------------


class TestReassignDraft:
    """POST /api/v1/drafts/{draft_id}/reassign — reassign reviewer (admin only)."""

    @pytest.mark.asyncio
    async def test_admin_reassigns_draft_gets_200(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
        admin_user: MagicMock,
    ) -> None:
        """Admin successfully reassigns a draft to a new reviewer."""
        draft_id = uuid.uuid4()
        email_id = uuid.uuid4()
        new_reviewer_id = uuid.uuid4()

        draft = _make_mock_draft(draft_id=draft_id, email_id=email_id)
        new_reviewer = MagicMock(spec=User)
        new_reviewer.id = new_reviewer_id
        new_reviewer.role = UserRole.REVIEWER
        email = _make_mock_email(email_id=email_id)

        # reassign_draft loads: draft, reviewer, email, classification (opt.)
        mock_db.execute.side_effect = [
            _scalar_result(draft),  # draft lookup
            _scalar_result(new_reviewer),  # reviewer lookup
            _scalar_result(email),  # email for response
            _scalar_result(None),  # classification (none)
        ]
        mock_db.refresh.return_value = None

        payload = {"reviewer_id": str(new_reviewer_id)}
        response = await admin_client.post(f"/api/v1/drafts/{draft_id}/reassign", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(draft_id)

    @pytest.mark.asyncio
    async def test_reviewer_cannot_reassign_gets_403(self, reviewer_client: AsyncClient) -> None:
        """Reviewer cannot reassign drafts — admin only endpoint."""
        payload = {"reviewer_id": str(uuid.uuid4())}
        response = await reviewer_client.post(
            f"/api/v1/drafts/{uuid.uuid4()}/reassign", json=payload
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_draft_gets_404(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Reassigning a non-existent draft returns 404."""
        mock_db.execute.return_value = _scalar_result(None)  # draft not found

        payload = {"reviewer_id": str(uuid.uuid4())}
        response = await admin_client.post(f"/api/v1/drafts/{uuid.uuid4()}/reassign", json=payload)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_reviewer_gets_404(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Reassigning to a non-existent reviewer returns 404."""
        draft_id = uuid.uuid4()
        draft = _make_mock_draft(draft_id=draft_id)

        mock_db.execute.side_effect = [
            _scalar_result(draft),  # draft found
            _scalar_result(None),  # reviewer not found
        ]

        payload = {"reviewer_id": str(uuid.uuid4())}
        response = await admin_client.post(f"/api/v1/drafts/{draft_id}/reassign", json=payload)
        assert response.status_code == 404
