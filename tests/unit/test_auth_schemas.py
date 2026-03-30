"""Unit tests for src/api/schemas/auth.py.

Pydantic schema validation tests — no database, no network, no Redis.
Each schema is tested for valid construction, boundary violations, and
structural guarantees (no password_hash leak, from_attributes enabled).

All schema fields are typed; no dict[str, Any].
"""

import uuid

import pytest
from pydantic import ValidationError

from src.api.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserResponse
from src.models.user import UserRole

# ---------------------------------------------------------------------------
# TestLoginRequest
# ---------------------------------------------------------------------------


class TestLoginRequest:
    """POST /auth/login request body.

    Invariants:
    - username: non-empty, max 100 chars.
    - password: non-empty (plaintext, never stored).
    """

    def test_valid_request(self) -> None:
        schema = LoginRequest(username="alice", password="s3cret!")

        assert schema.username == "alice"
        assert schema.password == "s3cret!"

    def test_missing_username_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(password="s3cret!")  # type: ignore[call-arg]

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("username",) for e in errors)

    def test_missing_password_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(username="alice")  # type: ignore[call-arg]

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("password",) for e in errors)

    def test_empty_username_raises(self) -> None:
        """min_length=1: empty string is invalid."""
        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(username="", password="s3cret!")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("username",) for e in errors)

    def test_username_exceeds_max_length_raises(self) -> None:
        """max_length=100: 101-char username must be rejected."""
        long_username = "a" * 101

        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(username=long_username, password="s3cret!")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("username",) for e in errors)

    def test_username_at_max_length_accepted(self) -> None:
        """Exactly 100 characters must be accepted."""
        username_100 = "u" * 100
        schema = LoginRequest(username=username_100, password="s3cret!")

        assert len(schema.username) == 100

    def test_empty_password_raises(self) -> None:
        """min_length=1: empty password is invalid."""
        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(username="alice", password="")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("password",) for e in errors)


# ---------------------------------------------------------------------------
# TestTokenResponse
# ---------------------------------------------------------------------------


class TestTokenResponse:
    """Successful auth response: access_token + refresh_token + token_type.

    Guarantee: token_type defaults to "bearer" if not supplied.
    """

    def test_valid_response(self) -> None:
        schema = TokenResponse(
            access_token="jwt.access.token",
            refresh_token="uuid-refresh-token",
            token_type="bearer",
        )

        assert schema.access_token == "jwt.access.token"
        assert schema.refresh_token == "uuid-refresh-token"
        assert schema.token_type == "bearer"

    def test_token_type_defaults_to_bearer(self) -> None:
        """token_type must default to 'bearer' when not provided."""
        schema = TokenResponse(
            access_token="jwt.access.token",
            refresh_token="uuid-refresh-token",
        )

        assert schema.token_type == "bearer"

    def test_explicit_token_type(self) -> None:
        """Explicit token_type overrides the default."""
        schema = TokenResponse(
            access_token="jwt.access.token",
            refresh_token="uuid-refresh-token",
            token_type="Bearer",
        )

        assert schema.token_type == "Bearer"


# ---------------------------------------------------------------------------
# TestRefreshRequest
# ---------------------------------------------------------------------------


class TestRefreshRequest:
    """POST /auth/refresh request body.

    Invariant: refresh_token is non-empty (opaque UUID from prior login).
    """

    def test_valid_request(self) -> None:
        refresh_token = str(uuid.uuid4())
        schema = RefreshRequest(refresh_token=refresh_token)

        assert schema.refresh_token == refresh_token

    def test_empty_refresh_token_raises(self) -> None:
        """min_length=1: empty refresh_token must be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RefreshRequest(refresh_token="")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("refresh_token",) for e in errors)


# ---------------------------------------------------------------------------
# TestUserResponse
# ---------------------------------------------------------------------------


class TestUserResponse:
    """GET /auth/me — safe user representation.

    Structural guarantees:
    - from_attributes=True enables ORM model construction.
    - password_hash is NOT exposed (not in model_fields).
    - role is a UserRole enum member.
    """

    def test_valid_construction(self) -> None:
        user_id = uuid.uuid4()
        schema = UserResponse(
            id=user_id,
            username="alice",
            role=UserRole.REVIEWER,
            is_active=True,
        )

        assert schema.id == user_id
        assert schema.username == "alice"
        assert schema.role is UserRole.REVIEWER
        assert schema.is_active is True

    def test_from_attributes_enabled(self) -> None:
        """ORM mode must be enabled so FastAPI can construct this from a SQLAlchemy User."""
        config = UserResponse.model_config

        assert config.get("from_attributes") is True, (
            "UserResponse must have from_attributes=True for ORM construction"
        )

    def test_no_password_hash_field(self) -> None:
        """password_hash must never appear in the response schema.

        Security boundary: the User ORM model has password_hash, but
        UserResponse must not expose it — from_attributes maps only declared fields.
        """
        assert "password_hash" not in UserResponse.model_fields, (
            "password_hash must not be in UserResponse — it would leak the bcrypt hash"
        )

    def test_role_is_enum_type(self) -> None:
        """role field annotation must be UserRole (StrEnum), not a bare str."""
        user_id = uuid.uuid4()
        schema = UserResponse(
            id=user_id,
            username="bob",
            role=UserRole.ADMIN,
            is_active=False,
        )

        assert isinstance(schema.role, UserRole), (
            f"role must be a UserRole member, got {type(schema.role)}"
        )

    def test_role_accepts_string_value(self) -> None:
        """Pydantic coerces string values to enum members for StrEnum fields."""
        user_id = uuid.uuid4()
        schema = UserResponse(
            id=user_id,
            username="carol",
            role="admin",
            is_active=True,
        )

        assert schema.role is UserRole.ADMIN

    def test_invalid_role_raises(self) -> None:
        """Unrecognised role value must raise ValidationError."""
        user_id = uuid.uuid4()

        with pytest.raises(ValidationError) as exc_info:
            UserResponse(
                id=user_id,
                username="dan",
                role="superuser",
                is_active=True,
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("role",) for e in errors)

    def test_admin_role_construction(self) -> None:
        user_id = uuid.uuid4()
        schema = UserResponse(
            id=user_id,
            username="admin-user",
            role=UserRole.ADMIN,
            is_active=True,
        )

        assert schema.role is UserRole.ADMIN
        assert schema.role.value == "admin"  # StrEnum .value is the underlying string
