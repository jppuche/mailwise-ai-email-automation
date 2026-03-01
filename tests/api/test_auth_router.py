"""Tests for auth router paths under /api/v1/auth/.

Scope: path mounting, 401/403 enforcement, schema validation.
These are unit tests — no real DB or Redis. Auth internals
(JWT signing, Redis token storage) are NOT tested here; those
belong in tests/unit/ and tests/integration/.

Fixtures from tests/api/conftest.py:
  client               — unauthenticated, mock_db NOT overridden
  admin_client         — Admin user + mock_db override
  unauthenticated_client — mock_db override, no auth override
"""

from httpx import AsyncClient


class TestAuthRouterMounting:
    """Verify that auth endpoints are mounted at /api/v1/auth/*."""

    async def test_login_path_exists(self, client: AsyncClient) -> None:
        """POST /api/v1/auth/login is reachable (returns non-404).

        The endpoint requires a real DB to validate credentials, so it may
        return 422 (invalid body) or 5xx without overrides. What matters is
        the path is mounted.
        """
        response = await client.post("/api/v1/auth/login", json={"username": "x", "password": "y"})
        assert response.status_code != 404

    async def test_refresh_path_exists(self, client: AsyncClient) -> None:
        """POST /api/v1/auth/refresh is reachable (returns non-404)."""
        response = await client.post("/api/v1/auth/refresh", json={"refresh_token": "some-token"})
        assert response.status_code != 404

    async def test_old_paths_without_api_v1_prefix_are_404(self, client: AsyncClient) -> None:
        """Paths without the /api/v1 prefix return 404.

        The app mounts all routers under /api/v1 — bare /auth/* must not exist.
        """
        response = await client.post("/auth/login", json={"username": "x", "password": "y"})
        assert response.status_code == 404


class TestAuthMeEndpoint:
    """GET /api/v1/auth/me — authentication enforcement and response shape."""

    async def test_me_without_token_returns_401(self, unauthenticated_client: AsyncClient) -> None:
        """GET /auth/me without a Bearer token returns 401.

        Relies on HTTPBearer(auto_error=False) + our AuthenticationError handler.
        """
        response = await unauthenticated_client.get("/api/v1/auth/me")
        assert response.status_code == 401

    async def test_me_401_response_has_error_field(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """401 response body uses ErrorResponse schema with 'error' field."""
        response = await unauthenticated_client.get("/api/v1/auth/me")
        data = response.json()
        assert "error" in data
        assert data["error"] == "unauthorized"

    async def test_me_with_admin_token_returns_200(self, admin_client: AsyncClient) -> None:
        """GET /auth/me with valid admin credentials returns 200."""
        response = await admin_client.get("/api/v1/auth/me")
        assert response.status_code == 200

    async def test_me_response_includes_username_and_role(self, admin_client: AsyncClient) -> None:
        """GET /auth/me response includes username and role fields."""
        response = await admin_client.get("/api/v1/auth/me")
        data = response.json()
        assert "username" in data
        assert "role" in data

    async def test_me_response_excludes_password_hash(self, admin_client: AsyncClient) -> None:
        """GET /auth/me never exposes password_hash in the response body."""
        response = await admin_client.get("/api/v1/auth/me")
        data = response.json()
        assert "password_hash" not in data
        assert "password" not in data


class TestAuthLogoutEndpoint:
    """POST /api/v1/auth/logout — authentication enforcement."""

    async def test_logout_without_token_returns_401(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """POST /auth/logout without a Bearer token returns 401.

        Logout requires an authenticated session — the bearer token identifies
        the session to revoke.
        """
        response = await unauthenticated_client.post(
            "/api/v1/auth/logout", json={"refresh_token": "some-opaque-token"}
        )
        assert response.status_code == 401

    async def test_logout_path_exists(self, client: AsyncClient) -> None:
        """POST /api/v1/auth/logout is mounted (non-404 response)."""
        response = await client.post("/api/v1/auth/logout", json={"refresh_token": "some-token"})
        assert response.status_code != 404


class TestAuthLoginValidation:
    """POST /api/v1/auth/login — request body validation (no DB needed)."""

    async def test_login_missing_username_returns_422(self, client: AsyncClient) -> None:
        """Login with missing 'username' field returns 422 Unprocessable Entity."""
        response = await client.post("/api/v1/auth/login", json={"password": "secret"})
        assert response.status_code == 422

    async def test_login_missing_password_returns_422(self, client: AsyncClient) -> None:
        """Login with missing 'password' field returns 422 Unprocessable Entity."""
        response = await client.post("/api/v1/auth/login", json={"username": "admin"})
        assert response.status_code == 422

    async def test_login_empty_username_returns_422(self, client: AsyncClient) -> None:
        """Login with empty string username returns 422 (min_length=1)."""
        response = await client.post(
            "/api/v1/auth/login", json={"username": "", "password": "secret"}
        )
        assert response.status_code == 422

    async def test_login_empty_password_returns_422(self, client: AsyncClient) -> None:
        """Login with empty string password returns 422 (min_length=1)."""
        response = await client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": ""}
        )
        assert response.status_code == 422
