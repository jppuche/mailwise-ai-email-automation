"""FastAPI dependencies for authentication and authorization.

tighten-types D4: get_current_user returns User (SQLAlchemy model), not Any.
try-except D7: Token extraction uses structured exception handling.
"""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_async_db
from src.core.exceptions import AuthenticationError, AuthorizationError
from src.core.security import TokenPayload, verify_access_token
from src.models.user import User, UserRole

# auto_error=False: we raise our own AuthenticationError (401), not FastAPI's default 403.
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> User:
    """Extract and validate the JWT, then load the User from DB.

    Returns User (SQLAlchemy model) — never Any.

    Raises AuthenticationError on: missing token, invalid/expired JWT,
    user not found, user inactive.
    """
    if credentials is None:
        raise AuthenticationError("Missing authentication token")

    payload: TokenPayload = verify_access_token(credentials.credentials)

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()

    if user is None:
        raise AuthenticationError("User not found")

    if not user.is_active:
        raise AuthenticationError("User account is disabled")

    return user


async def require_admin(
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> User:
    """Dependency that enforces Admin role.

    Raises AuthorizationError (403) if user is not Admin.
    """
    if current_user.role != UserRole.ADMIN:
        raise AuthorizationError("Admin access required")
    return current_user


async def require_reviewer_or_admin(
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> User:
    """Dependency that allows both Admin and Reviewer roles.

    Raises AuthorizationError (403) if user has neither role.
    """
    if current_user.role not in (UserRole.ADMIN, UserRole.REVIEWER):
        raise AuthorizationError("Reviewer or Admin access required")
    return current_user
