"""Auth router — login, refresh, logout, me.

Security invariants:
  - Login failure: same 401 message for wrong password AND nonexistent user
    (no user existence leak).
  - Passwords never in logs — LoginRequest.password consumed inline.
  - Refresh tokens are opaque UUIDs, not JWTs.
"""

import contextlib

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.redis_client import (
    RedisClientError,
    delete_refresh_token,
    get_refresh_token,
    set_refresh_token,
)
from src.api.deps import get_current_user
from src.api.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)
from src.core.database import get_async_db
from src.core.security import (
    _DUMMY_HASH,
    create_access_token,
    create_refresh_token,
    verify_password,
)
from src.models.user import User

logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> TokenResponse:
    """Authenticate user and return access + refresh tokens.

    Same 401 for wrong password and nonexistent user (no user enumeration).
    Logs username only — NEVER the password.
    """
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    # Constant-time password check: always call verify_password regardless of
    # whether the user exists.  Using _DUMMY_HASH when user is None prevents a
    # timing oracle that would allow username enumeration (username enumeration prevention).
    password_hash = user.password_hash if user is not None else _DUMMY_HASH
    password_valid = verify_password(body.password, password_hash)

    if user is None or not password_valid:
        logger.warning("login_failed", username=body.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_active:
        logger.warning("login_inactive_user", username=body.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    access_token = create_access_token(user.id, user.role.value)
    refresh_token = create_refresh_token()

    try:
        await set_refresh_token(refresh_token, str(user.id))
    except RedisClientError:
        logger.error("redis_store_refresh_failed", user_id=str(user.id))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        ) from None

    logger.info("login_success", user_id=str(user.id))
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> TokenResponse:
    """Exchange a valid refresh token for new tokens.

    Refresh token rotation: old token deleted, new one issued.
    """
    try:
        user_id = await get_refresh_token(body.refresh_token)
    except RedisClientError:
        logger.error("redis_get_refresh_failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        ) from None

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        with contextlib.suppress(RedisClientError):
            await delete_refresh_token(body.refresh_token)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Rotate: delete old, create new
    with contextlib.suppress(RedisClientError):
        await delete_refresh_token(body.refresh_token)

    new_access_token = create_access_token(user.id, user.role.value)
    new_refresh_token = create_refresh_token()

    try:
        await set_refresh_token(new_refresh_token, str(user.id))
    except RedisClientError:
        logger.error("redis_store_refresh_failed", user_id=str(user.id))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        ) from None

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: RefreshRequest,
    _current_user: User = Depends(get_current_user),  # noqa: B008
) -> None:
    """Revoke a refresh token (logout).

    Requires valid access token (authenticated to logout).
    """
    try:
        await delete_refresh_token(body.refresh_token)
    except RedisClientError:
        logger.error("redis_delete_refresh_failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        ) from None


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> UserResponse:
    """Return the authenticated user's profile.

    UserResponse excludes password_hash — safe to return.
    """
    return UserResponse.model_validate(current_user)
