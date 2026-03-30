"""Pydantic schemas for auth endpoints.

No dict[str, Any]. All fields are typed.
UserRole imported from ORM model enum — single source of truth.
"""

import uuid

from pydantic import BaseModel, Field

from src.models.user import UserRole


class LoginRequest(BaseModel):
    """POST /auth/login request body.

    Invariants:
      - username: non-empty str, max 100 chars (mirrors DB constraint).
      - password: non-empty str (plaintext, NEVER logged or persisted).
    """

    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Successful auth response: access token + refresh token.

    Guarantees:
      - access_token: JWT string (HS256-signed).
      - refresh_token: opaque UUID (not a JWT — no decodable user info).
      - token_type: always "bearer".
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """POST /auth/refresh request body.

    Invariants:
      - refresh_token: non-empty str (opaque UUID from prior login).
    """

    refresh_token: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    """GET /auth/me response — safe user representation (no password_hash).

    model_config: from_attributes=True enables ORM mode
    (construct from SQLAlchemy model instance).
    """

    model_config = {"from_attributes": True}

    id: uuid.UUID
    username: str
    role: UserRole
    is_active: bool
