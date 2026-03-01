"""Integration tests for auth endpoints: /api/v1/auth/login, /refresh, /logout, /me.

All tests require a running PostgreSQL + Redis instance.
Run with: pytest tests/integration/ --run-integration

Security invariants verified:
  - Login: identical 401 detail for wrong password AND nonexistent user (no
    user enumeration).
  - Refresh token rotation: old token revoked on refresh, not reusable.
  - Logout: access token required; refresh token revoked.
  - /me: password_hash never present in response.

try-except D8: Tests use conditionals (assert) not try/except — response
parsing is local computation over known shapes.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import Depends
from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.deps import require_admin, require_reviewer_or_admin
from src.api.main import app
from src.core.config import get_settings
from src.core.security import hash_password
from src.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Test-only endpoints for RBAC verification — registered once at module load.
# These endpoints exist only in the test process; they are NOT in production.
# ---------------------------------------------------------------------------


@app.get("/test-admin-only")
async def _test_admin_only(user: User = Depends(require_admin)) -> dict[str, str]:  # noqa: B008
    return {"role": user.role.value}


@app.get("/test-reviewer-or-admin")
async def _test_reviewer_or_admin(
    user: User = Depends(require_reviewer_or_admin),  # noqa: B008
) -> dict[str, str]:
    return {"role": user.role.value}


# ---------------------------------------------------------------------------
# TestLoginEndpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestLoginEndpoint:
    """POST /api/v1/auth/login — credential verification, token issuance."""

    @pytest.mark.asyncio
    async def test_login_success(
        self,
        async_client: AsyncClient,
        admin_user: User,
    ) -> None:
        """Valid credentials return 200 with access_token, refresh_token, token_type."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={"username": admin_user.username, "password": "admin_pass_123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0
        assert isinstance(data["refresh_token"], str)
        assert len(data["refresh_token"]) > 0

    @pytest.mark.asyncio
    async def test_login_wrong_password(
        self,
        async_client: AsyncClient,
        admin_user: User,
    ) -> None:
        """Wrong password returns 401 with 'Invalid credentials'."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={"username": admin_user.username, "password": "wrong_password"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Nonexistent username returns 401 — same message as wrong password."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={"username": "nonexistent_user_xyz", "password": "any_password"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_login_same_error_for_both(
        self,
        async_client: AsyncClient,
        admin_user: User,
    ) -> None:
        """Wrong-password and nonexistent-user return identical detail string.

        Security invariant: no user enumeration. An attacker cannot
        distinguish a valid username with a wrong password from an invalid
        username by inspecting the error message.
        """
        wrong_password_response = await async_client.post(
            "/api/v1/auth/login",
            json={"username": admin_user.username, "password": "wrong_password"},
        )
        nonexistent_response = await async_client.post(
            "/api/v1/auth/login",
            json={"username": "completely_nonexistent_user", "password": "any_pass"},
        )
        assert wrong_password_response.status_code == 401
        assert nonexistent_response.status_code == 401
        assert wrong_password_response.json()["detail"] == nonexistent_response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_inactive_user(
        self,
        async_client: AsyncClient,
        override_db: None,
    ) -> None:
        """Inactive user returns 401 — same message as invalid credentials.

        An inactive account must not reveal that the username/password are
        actually correct — same 401 detail is required.
        """
        settings = get_settings()
        engine = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)
        SessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            engine, expire_on_commit=False
        )

        suffix = uuid.uuid4().hex[:8]
        inactive_user = User(
            username=f"test_inactive_{suffix}",
            password_hash=hash_password("inactive_pass_123"),
            role=UserRole.REVIEWER,
            is_active=False,
        )

        async with SessionFactory() as session:
            session.add(inactive_user)
            await session.commit()
            await session.refresh(inactive_user)

        try:
            response = await async_client.post(
                "/api/v1/auth/login",
                json={
                    "username": inactive_user.username,
                    "password": "inactive_pass_123",
                },
            )
            assert response.status_code == 401
            assert response.json()["detail"] == "Invalid credentials"
        finally:
            async with SessionFactory() as session:
                db_user = await session.get(User, inactive_user.id)
                if db_user is not None:
                    await session.delete(db_user)
                    await session.commit()
            await engine.dispose()


# ---------------------------------------------------------------------------
# TestRefreshEndpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRefreshEndpoint:
    """POST /api/v1/auth/refresh — token rotation."""

    @pytest.mark.asyncio
    async def test_refresh_returns_new_tokens(
        self,
        async_client: AsyncClient,
        admin_user: User,
    ) -> None:
        """Valid refresh token returns 200 with new access_token and refresh_token."""
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={"username": admin_user.username, "password": "admin_pass_123"},
        )
        assert login_response.status_code == 200
        refresh_token = login_response.json()["refresh_token"]

        response = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Random UUID refresh token returns 401."""
        response = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": str(uuid.uuid4())},
        )
        assert response.status_code == 401
        assert "refresh token" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_refresh_rotates_old_token(
        self,
        async_client: AsyncClient,
        admin_user: User,
    ) -> None:
        """After refresh, the old refresh token is revoked and cannot be reused.

        Security invariant: refresh token rotation. Each token is single-use.
        An attacker who steals a refresh token cannot reuse it after the
        legitimate holder has already refreshed.
        """
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={"username": admin_user.username, "password": "admin_pass_123"},
        )
        assert login_response.status_code == 200
        old_refresh_token = login_response.json()["refresh_token"]

        # First refresh succeeds and rotates the token.
        first_refresh = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh_token},
        )
        assert first_refresh.status_code == 200

        # Replaying the old token is rejected — token rotation enforced.
        second_refresh = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh_token},
        )
        assert second_refresh.status_code == 401


# ---------------------------------------------------------------------------
# TestLogoutEndpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestLogoutEndpoint:
    """POST /api/v1/auth/logout — token revocation."""

    @pytest.mark.asyncio
    async def test_logout_success(
        self,
        async_client: AsyncClient,
        admin_user: User,
    ) -> None:
        """Authenticated logout returns 204 No Content."""
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={"username": admin_user.username, "password": "admin_pass_123"},
        )
        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]
        refresh_token = login_response.json()["refresh_token"]

        response = await async_client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_logout_requires_auth(
        self,
        async_client: AsyncClient,
        admin_user: User,
    ) -> None:
        """Logout without Bearer token returns 401."""
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={"username": admin_user.username, "password": "admin_pass_123"},
        )
        assert login_response.status_code == 200
        refresh_token = login_response.json()["refresh_token"]

        response = await async_client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
            # No Authorization header.
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_after_logout_fails(
        self,
        async_client: AsyncClient,
        admin_user: User,
    ) -> None:
        """After logout, the refresh token is revoked and cannot be used.

        Security invariant: logout revokes the refresh token server-side.
        An attacker who steals the refresh token after logout cannot use it
        to obtain new access tokens.
        """
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={"username": admin_user.username, "password": "admin_pass_123"},
        )
        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]
        refresh_token = login_response.json()["refresh_token"]

        logout_response = await async_client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert logout_response.status_code == 204

        refresh_response = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_response.status_code == 401


# ---------------------------------------------------------------------------
# TestMeEndpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMeEndpoint:
    """GET /api/v1/auth/me — authenticated user profile."""

    @pytest.mark.asyncio
    async def test_me_returns_user_info(
        self,
        async_client: AsyncClient,
        admin_tokens: tuple[str, str],
        admin_user: User,
    ) -> None:
        """Authenticated request returns 200 with user profile fields."""
        access_token, _ = admin_tokens
        response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        assert "id" in data
        assert "username" in data
        assert "role" in data
        assert "is_active" in data
        assert data["username"] == admin_user.username
        assert data["role"] == UserRole.ADMIN.value
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_me_without_token(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Request without Authorization header returns 401."""
        response = await async_client.get("/api/v1/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_me_with_expired_token(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Expired JWT returns 401.

        Token is constructed manually with exp set in the past.
        This tests the expiry check in verify_access_token(), which uses
        try/except ExpiredSignatureError (D7) — a structured external-state
        check on the jose library's parsing result.
        """
        settings = get_settings()
        past = datetime.now(UTC) - timedelta(minutes=30)
        expired_payload = {
            "sub": str(uuid.uuid4()),
            "role": "admin",
            "exp": int(past.timestamp()),
        }
        expired_token = jwt.encode(
            expired_payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_me_response_excludes_password_hash(
        self,
        async_client: AsyncClient,
        admin_tokens: tuple[str, str],
    ) -> None:
        """password_hash must NEVER appear in the /me response.

        Security invariant: UserResponse schema (from_attributes=True ORM mode)
        must not accidentally expose the hash through field aliasing or extra
        attribute leakage.
        """
        access_token, _ = admin_tokens
        response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        assert "password_hash" not in response.json()


# ---------------------------------------------------------------------------
# TestRoleBasedAccess
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRoleBasedAccess:
    """RBAC enforcement via require_admin and require_reviewer_or_admin deps."""

    @pytest.mark.asyncio
    async def test_admin_endpoint_rejects_reviewer(
        self,
        async_client: AsyncClient,
        reviewer_tokens: tuple[str, str],
    ) -> None:
        """Reviewer role is rejected by require_admin dependency (403)."""
        access_token, _ = reviewer_tokens
        response = await async_client.get(
            "/test-admin-only",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_reviewer_or_admin_accepts_both(
        self,
        async_client: AsyncClient,
        reviewer_tokens: tuple[str, str],
        admin_tokens: tuple[str, str],
    ) -> None:
        """Both Reviewer and Admin are accepted by require_reviewer_or_admin (200)."""
        reviewer_access, _ = reviewer_tokens
        reviewer_response = await async_client.get(
            "/test-reviewer-or-admin",
            headers={"Authorization": f"Bearer {reviewer_access}"},
        )
        assert reviewer_response.status_code == 200
        assert reviewer_response.json()["role"] == UserRole.REVIEWER.value

        admin_access, _ = admin_tokens
        admin_response = await async_client.get(
            "/test-reviewer-or-admin",
            headers={"Authorization": f"Bearer {admin_access}"},
        )
        assert admin_response.status_code == 200
        assert admin_response.json()["role"] == UserRole.ADMIN.value
