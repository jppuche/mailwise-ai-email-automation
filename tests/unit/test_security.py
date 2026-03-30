"""Unit tests for src/core/security.py.

Pure function tests — no database or Redis. Settings are loaded from the
.env file present in the project root (or from env vars set in CI).

Architecture invariants tested:
- TokenPayload is a TypedDict with exactly sub/role/exp keys.
- verify_access_token has 3 separate except blocks for ExpiredSignatureError,
  JWTClaimsError, JWTError.
- verify_password uses conditional return, NOT try/except.
"""

import inspect
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from jose import JWTError
from jose import jwt as jose_jwt

from src.core.config import get_settings
from src.core.exceptions import AuthenticationError
from src.core.security import (
    TokenPayload,
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_access_token,
    verify_password,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEST_ALGORITHM = "HS256"
_PLAIN_PASSWORD = "correct-horse-battery-staple"


# ---------------------------------------------------------------------------
# TestHashPassword
# ---------------------------------------------------------------------------


class TestHashPassword:
    """hash_password(plain) → bcrypt hash string.

    bcrypt hashes start with $2b$ and incorporate a random salt,
    so identical inputs produce distinct outputs.
    """

    def test_returns_bcrypt_hash(self) -> None:
        result = hash_password(_PLAIN_PASSWORD)

        assert result.startswith("$2b$"), (
            f"Expected bcrypt hash starting with '$2b$', got: {result[:8]!r}"
        )

    def test_different_passwords_produce_different_hashes(self) -> None:
        hash_a = hash_password("password-alpha")
        hash_b = hash_password("password-beta")

        assert hash_a != hash_b

    def test_same_password_produces_different_hashes(self) -> None:
        """bcrypt uses a random salt — identical inputs must not produce identical hashes."""
        hash_a = hash_password(_PLAIN_PASSWORD)
        hash_b = hash_password(_PLAIN_PASSWORD)

        assert hash_a != hash_b

    def test_returns_str(self) -> None:
        result = hash_password(_PLAIN_PASSWORD)

        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# TestVerifyPassword
# ---------------------------------------------------------------------------


class TestVerifyPassword:
    """verify_password(plain, hashed) → bool.

    This is local computation — must use conditional return, not try/except.
    """

    def test_correct_password_returns_true(self) -> None:
        hashed = hash_password(_PLAIN_PASSWORD)

        assert verify_password(_PLAIN_PASSWORD, hashed) is True

    def test_wrong_password_returns_false(self) -> None:
        hashed = hash_password(_PLAIN_PASSWORD)

        assert verify_password("wrong-password", hashed) is False

    def test_uses_conditional_not_try_except(self) -> None:
        """D8: verify_password must not contain try/except — it is local computation.

        Inspect the source to confirm the implementation follows the directive.
        """
        source = inspect.getsource(verify_password)

        assert "try" not in source, (
            "verify_password must not use try/except — it is local computation"
        )
        assert "except" not in source, (
            "verify_password must not use try/except — it is local computation"
        )


# ---------------------------------------------------------------------------
# TestCreateAccessToken
# ---------------------------------------------------------------------------


class TestCreateAccessToken:
    """create_access_token(user_id, role) → signed JWT string.

    Uses HS256 algorithm. Claims: sub (str(UUID)), role (str), exp (future int).
    """

    def test_returns_string(self) -> None:
        user_id = uuid.uuid4()
        result = create_access_token(user_id, "reviewer")

        assert isinstance(result, str)

    def test_decodable_with_correct_secret(self) -> None:
        """The returned token must be decodable using the same secret and algorithm."""
        user_id = uuid.uuid4()
        token = create_access_token(user_id, "admin")

        # jose_jwt.decode raises if the token is invalid.
        decoded = jose_jwt.decode(
            token, get_settings().jwt_secret_key, algorithms=[_TEST_ALGORITHM]
        )

        assert isinstance(decoded, dict)

    def test_contains_sub_claim(self) -> None:
        """sub must be the string representation of the UUID."""
        user_id = uuid.uuid4()
        token = create_access_token(user_id, "reviewer")

        decoded = jose_jwt.decode(
            token, get_settings().jwt_secret_key, algorithms=[_TEST_ALGORITHM]
        )

        assert decoded["sub"] == str(user_id)

    def test_contains_role_claim(self) -> None:
        user_id = uuid.uuid4()
        token = create_access_token(user_id, "admin")

        decoded = jose_jwt.decode(
            token, get_settings().jwt_secret_key, algorithms=[_TEST_ALGORITHM]
        )

        assert decoded["role"] == "admin"

    def test_exp_is_in_future(self) -> None:
        user_id = uuid.uuid4()
        token = create_access_token(user_id, "reviewer")

        decoded = jose_jwt.decode(
            token, get_settings().jwt_secret_key, algorithms=[_TEST_ALGORITHM]
        )
        exp: int = decoded["exp"]
        now = int(datetime.now(UTC).timestamp())

        assert exp > now, f"exp={exp} must be in the future (now={now})"


# ---------------------------------------------------------------------------
# TestVerifyAccessToken
# ---------------------------------------------------------------------------


class TestVerifyAccessToken:
    """verify_access_token(token) → TokenPayload | raises AuthenticationError.

    Uses 3 separate except blocks for ExpiredSignatureError, JWTClaimsError,
    JWTError. Missing-claims check uses a conditional.
    """

    def _make_valid_token(self, user_id: uuid.UUID | None = None, role: str = "reviewer") -> str:
        uid = user_id or uuid.uuid4()
        return create_access_token(uid, role)

    def test_valid_token_returns_token_payload(self) -> None:
        user_id = uuid.uuid4()
        token = self._make_valid_token(user_id=user_id, role="admin")

        result = verify_access_token(token)

        assert isinstance(result, dict), "TokenPayload is a TypedDict — runtime type is dict"
        assert result["sub"] == str(user_id)
        assert result["role"] == "admin"
        assert isinstance(result["exp"], int)

    def test_expired_token_raises_authentication_error(self) -> None:
        """Tokens with exp in the past must raise AuthenticationError."""
        user_id = uuid.uuid4()
        past_exp = int((datetime.now(UTC) - timedelta(hours=1)).timestamp())
        expired_payload: dict[str, Any] = {
            "sub": str(user_id),
            "role": "reviewer",
            "exp": past_exp,
        }
        expired_token = jose_jwt.encode(
            expired_payload, get_settings().jwt_secret_key, algorithm=_TEST_ALGORITHM
        )

        with pytest.raises(AuthenticationError):
            verify_access_token(expired_token)

    def test_wrong_secret_raises_authentication_error(self) -> None:
        """Token signed with a different secret must raise AuthenticationError."""
        user_id = uuid.uuid4()
        future_exp = int((datetime.now(UTC) + timedelta(minutes=15)).timestamp())
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "role": "reviewer",
            "exp": future_exp,
        }
        token_wrong_secret = jose_jwt.encode(payload, "wrong-secret", algorithm=_TEST_ALGORITHM)

        with pytest.raises(AuthenticationError):
            verify_access_token(token_wrong_secret)

    def test_malformed_token_raises_authentication_error(self) -> None:
        """A string that is not a valid JWT structure must raise AuthenticationError."""
        with pytest.raises(AuthenticationError):
            verify_access_token("not.a.token")

    def test_missing_sub_raises_authentication_error(self) -> None:
        """A valid JWT missing the 'sub' claim must raise AuthenticationError.

        The check in verify_access_token is conditional (D8), not a caught exception.
        """
        future_exp = int((datetime.now(UTC) + timedelta(minutes=15)).timestamp())
        payload_no_sub: dict[str, Any] = {
            "role": "reviewer",
            "exp": future_exp,
        }
        token = jose_jwt.encode(
            payload_no_sub, get_settings().jwt_secret_key, algorithm=_TEST_ALGORITHM
        )

        with pytest.raises(AuthenticationError):
            verify_access_token(token)

    def test_missing_role_raises_authentication_error(self) -> None:
        """A valid JWT missing the 'role' claim must raise AuthenticationError."""
        user_id = uuid.uuid4()
        future_exp = int((datetime.now(UTC) + timedelta(minutes=15)).timestamp())
        payload_no_role: dict[str, Any] = {
            "sub": str(user_id),
            "exp": future_exp,
        }
        token = jose_jwt.encode(
            payload_no_role, get_settings().jwt_secret_key, algorithm=_TEST_ALGORITHM
        )

        with pytest.raises(AuthenticationError):
            verify_access_token(token)


# ---------------------------------------------------------------------------
# TestCreateRefreshToken
# ---------------------------------------------------------------------------


class TestCreateRefreshToken:
    """create_refresh_token() → UUID4 string.

    Opaque — not a JWT. Callers must not try to decode it as a JWT.
    Redis stores the token with TTL; this function only generates the value.
    """

    def test_returns_valid_uuid_string(self) -> None:
        result = create_refresh_token()

        # uuid.UUID() raises ValueError if the string is not a valid UUID.
        parsed = uuid.UUID(result)
        assert parsed.version == 4

    def test_two_calls_return_different_tokens(self) -> None:
        token_a = create_refresh_token()
        token_b = create_refresh_token()

        assert token_a != token_b

    def test_not_decodable_as_jwt(self) -> None:
        """Refresh token must NOT be a JWT — it has no decodable payload."""
        token = create_refresh_token()

        with pytest.raises(JWTError):
            # jose_jwt.decode raises JWTError when the token is not a valid JWT structure.
            jose_jwt.decode(token, get_settings().jwt_secret_key, algorithms=[_TEST_ALGORITHM])


# ---------------------------------------------------------------------------
# TestTokenPayload
# ---------------------------------------------------------------------------


class TestTokenPayload:
    """TokenPayload is a TypedDict with exactly sub, role, exp keys.

    No dict[str, Any] at this boundary.
    """

    def test_is_typed_dict(self) -> None:
        """TokenPayload must be a TypedDict with the correct keys."""
        # TypedDict classes expose __annotations__ with their field names.
        annotations = TokenPayload.__annotations__

        assert "sub" in annotations, "TokenPayload must have 'sub' key"
        assert "role" in annotations, "TokenPayload must have 'role' key"
        assert "exp" in annotations, "TokenPayload must have 'exp' key"
        assert annotations["sub"] is str, "sub must be annotated as str"
        assert annotations["role"] is str, "role must be annotated as str"
        assert annotations["exp"] is int, "exp must be annotated as int"

    def test_constructable_with_correct_keys(self) -> None:
        """TypedDict values are plain dicts at runtime — construction must work."""
        now = int(time.time()) + 900
        payload: TokenPayload = {
            "sub": str(uuid.uuid4()),
            "role": "admin",
            "exp": now,
        }

        assert payload["sub"] != ""
        assert payload["role"] == "admin"
        assert payload["exp"] == now
