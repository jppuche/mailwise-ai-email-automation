"""JWT token management and password hashing.

Pure functions — no database or Redis dependencies.
All external-state errors (jose decode failures) are caught
with specific exception types.

TokenPayload is TypedDict, not dict[str, Any].

Uses bcrypt directly (not passlib) — passlib 1.7.4 is unmaintained and
incompatible with bcrypt>=4.2 on Python 3.14 (detect_wrap_bug failure).
"""

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import TypedDict

import bcrypt
from jose import ExpiredSignatureError, JWTError, jwt
from jose.exceptions import JWTClaimsError

from src.core.config import get_settings
from src.core.exceptions import AuthenticationError

# Pre-computed bcrypt hash used during login when the requested user does not
# exist.  Calling verify_password() against this hash ensures constant-time
# behaviour regardless of whether the username is valid, preventing a timing
# oracle that could be used to enumerate valid usernames.
#
# The input is 32 cryptographically-random bytes so no text password can ever
# match it.  Rounds are fixed at 12 (matches bcrypt_rounds default) — this
# value is intentionally NOT derived from Settings so it is available at
# module import time without triggering settings validation.
_DUMMY_HASH: str = bcrypt.hashpw(
    os.urandom(32),
    bcrypt.gensalt(rounds=12),
).decode("utf-8")


class TokenPayload(TypedDict):
    """JWT payload structure.

    sub: user ID as string (UUID serialized).
    role: user role as string (UserRole.value).
    exp: expiration timestamp (Unix epoch int).
    """

    sub: str
    role: str
    exp: int


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with bcrypt.

    Returns bcrypt hash string ($2b$...).
    Rounds are loaded from Settings.bcrypt_rounds.
    """
    settings = get_settings()
    password_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext against bcrypt hash.

    Local computation — uses conditional return only.
    """
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    """Create a signed JWT access token.

    Returns HS256-signed JWT with sub, role, exp claims.
    Expires in jwt_access_ttl_minutes from now (UTC).
    """
    settings = get_settings()
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.jwt_access_ttl_minutes)
    payload: TokenPayload = {
        "sub": str(user_id),
        "role": role,
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)  # type: ignore[no-any-return]


def verify_access_token(token: str) -> TokenPayload:
    """Decode and verify a JWT access token.

    Uses separate catches per exception type.

    Raises AuthenticationError on any verification failure.
    """
    settings = get_settings()
    try:
        decoded = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except ExpiredSignatureError:
        raise AuthenticationError("Token has expired") from None
    except JWTClaimsError:
        raise AuthenticationError("Invalid token claims") from None
    except JWTError:
        raise AuthenticationError("Invalid token") from None

    if "sub" not in decoded or "role" not in decoded:
        raise AuthenticationError("Token missing required claims")

    return TokenPayload(
        sub=decoded["sub"],
        role=decoded["role"],
        exp=decoded["exp"],
    )


def create_refresh_token() -> str:
    """Generate an opaque refresh token (UUID4).

    NOT a JWT — no decodable user information.
    Storage and TTL handled by redis_client.
    """
    return str(uuid.uuid4())
