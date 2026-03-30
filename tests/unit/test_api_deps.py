"""Tests for src/api/deps.py — FastAPI dependency functions.

Coverage targets:
  1. get_current_user: missing credentials raises AuthenticationError
  2. get_current_user: valid token returns User
  3. get_current_user: user not found in DB raises AuthenticationError
  4. get_current_user: user inactive raises AuthenticationError
  5. require_admin: admin user passes through
  6. require_admin: reviewer raises AuthorizationError
  7. require_reviewer_or_admin: admin passes through
  8. require_reviewer_or_admin: reviewer passes through
  9. require_draft_access: admin sees all drafts
 10. require_draft_access: reviewer sees own drafts
 11. require_draft_access: reviewer denied access to other's draft
 12. require_draft_access: draft not found raises NotFoundError

Mocking strategy:
  - verify_access_token: patched to return controlled TokenPayload.
  - db: AsyncMock with execute.return_value configured per test.
  - User and Draft: MagicMock() to avoid SQLAlchemy instrumentation.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.deps import (
    get_current_user,
    require_admin,
    require_draft_access,
    require_reviewer_or_admin,
)
from src.core.exceptions import AuthenticationError, AuthorizationError, NotFoundError
from src.models.user import UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


def _make_user(
    *,
    user_id: uuid.UUID | None = None,
    role: UserRole = UserRole.ADMIN,
    is_active: bool = True,
) -> MagicMock:
    from src.models.user import User

    user = MagicMock(spec=User)
    user.id = user_id or uuid.uuid4()
    user.role = role
    user.is_active = is_active
    return user


def _make_draft(
    *,
    draft_id: uuid.UUID | None = None,
    reviewer_id: uuid.UUID | None = None,
) -> MagicMock:
    from src.models.draft import Draft

    draft = MagicMock(spec=Draft)
    draft.id = draft_id or uuid.uuid4()
    draft.reviewer_id = reviewer_id or uuid.uuid4()
    return draft


def _scalar_result(value: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _make_credentials(token: str = "valid.jwt.token") -> MagicMock:
    from fastapi.security import HTTPAuthorizationCredentials

    creds = MagicMock(spec=HTTPAuthorizationCredentials)
    creds.credentials = token
    return creds


def _make_token_payload(user_id: uuid.UUID, role: str = "admin") -> dict[str, object]:
    return {"sub": str(user_id), "role": role, "exp": 9999999999}


# ---------------------------------------------------------------------------
# TestGetCurrentUser
# ---------------------------------------------------------------------------


class TestGetCurrentUser:
    async def test_missing_credentials_raises_authentication_error(self) -> None:
        """No credentials header → AuthenticationError('Missing authentication token')."""
        db = _make_db()

        with pytest.raises(AuthenticationError, match="Missing"):
            await get_current_user(credentials=None, db=db)

    async def test_valid_token_returns_user(self) -> None:
        """Valid JWT + existing active user → returns User."""
        db = _make_db()
        user_id = uuid.uuid4()
        user = _make_user(user_id=user_id, role=UserRole.ADMIN, is_active=True)
        payload = _make_token_payload(user_id, role="admin")

        db.execute.return_value = _scalar_result(user)

        with patch("src.api.deps.verify_access_token", return_value=payload):
            result = await get_current_user(
                credentials=_make_credentials("valid.token"),
                db=db,
            )

        assert result is user

    async def test_user_not_found_raises_authentication_error(self) -> None:
        """Valid JWT but user missing from DB → AuthenticationError."""
        db = _make_db()
        user_id = uuid.uuid4()
        payload = _make_token_payload(user_id)

        db.execute.return_value = _scalar_result(None)

        with (
            patch("src.api.deps.verify_access_token", return_value=payload),
            pytest.raises(AuthenticationError, match="User not found"),
        ):
            await get_current_user(
                credentials=_make_credentials(),
                db=db,
            )

    async def test_inactive_user_raises_authentication_error(self) -> None:
        """Valid JWT but user.is_active=False → AuthenticationError."""
        db = _make_db()
        user_id = uuid.uuid4()
        user = _make_user(user_id=user_id, is_active=False)
        payload = _make_token_payload(user_id)

        db.execute.return_value = _scalar_result(user)

        with (
            patch("src.api.deps.verify_access_token", return_value=payload),
            pytest.raises(AuthenticationError, match="disabled"),
        ):
            await get_current_user(
                credentials=_make_credentials(),
                db=db,
            )


# ---------------------------------------------------------------------------
# TestRequireAdmin
# ---------------------------------------------------------------------------


class TestRequireAdmin:
    async def test_admin_user_passes_through(self) -> None:
        """Admin role → returns user unchanged."""
        user = _make_user(role=UserRole.ADMIN)

        result = await require_admin(current_user=user)

        assert result is user

    async def test_reviewer_raises_authorization_error(self) -> None:
        """Reviewer role → AuthorizationError."""
        user = _make_user(role=UserRole.REVIEWER)

        with pytest.raises(AuthorizationError, match="Admin"):
            await require_admin(current_user=user)


# ---------------------------------------------------------------------------
# TestRequireReviewerOrAdmin
# ---------------------------------------------------------------------------


class TestRequireReviewerOrAdmin:
    async def test_admin_passes_through(self) -> None:
        """Admin role → passes through."""
        user = _make_user(role=UserRole.ADMIN)

        result = await require_reviewer_or_admin(current_user=user)

        assert result is user

    async def test_reviewer_passes_through(self) -> None:
        """Reviewer role → passes through."""
        user = _make_user(role=UserRole.REVIEWER)

        result = await require_reviewer_or_admin(current_user=user)

        assert result is user


# ---------------------------------------------------------------------------
# TestRequireDraftAccess
# ---------------------------------------------------------------------------


class TestRequireDraftAccess:
    async def test_admin_can_access_any_draft(self) -> None:
        """Admin user can access drafts owned by any reviewer."""
        admin = _make_user(role=UserRole.ADMIN)
        draft_id = uuid.uuid4()
        draft = _make_draft(draft_id=draft_id, reviewer_id=uuid.uuid4())  # different owner
        db = _make_db()
        db.execute.return_value = _scalar_result(draft)

        result = await require_draft_access(
            draft_id=draft_id,
            current_user=admin,
            db=db,
        )

        assert result is draft

    async def test_reviewer_can_access_own_draft(self) -> None:
        """Reviewer can access draft where reviewer_id == current_user.id."""
        reviewer_id = uuid.uuid4()
        reviewer = _make_user(user_id=reviewer_id, role=UserRole.REVIEWER)
        draft_id = uuid.uuid4()
        draft = _make_draft(draft_id=draft_id, reviewer_id=reviewer_id)
        db = _make_db()
        db.execute.return_value = _scalar_result(draft)

        result = await require_draft_access(
            draft_id=draft_id,
            current_user=reviewer,
            db=db,
        )

        assert result is draft

    async def test_reviewer_denied_access_to_others_draft(self) -> None:
        """Reviewer cannot access draft owned by a different reviewer."""
        reviewer_id = uuid.uuid4()
        reviewer = _make_user(user_id=reviewer_id, role=UserRole.REVIEWER)
        draft_id = uuid.uuid4()
        # Draft is owned by a different user
        draft = _make_draft(draft_id=draft_id, reviewer_id=uuid.uuid4())
        db = _make_db()
        db.execute.return_value = _scalar_result(draft)

        with pytest.raises(AuthorizationError, match="not allowed"):
            await require_draft_access(
                draft_id=draft_id,
                current_user=reviewer,
                db=db,
            )

    async def test_draft_not_found_raises_not_found_error(self) -> None:
        """Non-existent draft raises NotFoundError."""
        admin = _make_user(role=UserRole.ADMIN)
        draft_id = uuid.uuid4()
        db = _make_db()
        db.execute.return_value = _scalar_result(None)

        with pytest.raises(NotFoundError, match="not found"):
            await require_draft_access(
                draft_id=draft_id,
                current_user=admin,
                db=db,
            )
