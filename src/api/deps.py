"""FastAPI dependencies for authentication and authorization.

get_current_user returns User (SQLAlchemy model), not Any.
Token extraction uses structured exception handling.
"""

import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_async_db
from src.core.exceptions import AuthenticationError, AuthorizationError, NotFoundError
from src.core.security import TokenPayload, verify_access_token
from src.models.draft import Draft
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


async def require_draft_access(
    draft_id: uuid.UUID,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_async_db),  # noqa: B008
) -> Draft:
    """Load Draft and enforce access: Admin sees all, Reviewer sees own only.

    Raises NotFoundError if draft does not exist.
    Raises AuthorizationError if Reviewer does not own the draft.
    """
    result = await db.execute(select(Draft).where(Draft.id == draft_id))
    draft = result.scalar_one_or_none()
    if draft is None:
        raise NotFoundError(f"Draft {draft_id} not found")
    if current_user.role != UserRole.ADMIN and draft.reviewer_id != current_user.id:
        raise AuthorizationError("Access to this draft is not allowed")
    return draft


async def get_routing_service():  # type: ignore[no-untyped-def]
    """DI factory for RoutingService. Creates adapters only if credentials exist."""
    from src.adapters.channel.base import ChannelAdapter
    from src.adapters.channel.schemas import ChannelCredentials
    from src.adapters.channel.slack import SlackAdapter
    from src.core.config import get_settings
    from src.services.routing import RoutingService

    settings = get_settings()
    channel_adapters: dict[str, ChannelAdapter] = {}
    if settings.slack_bot_token:
        slack = SlackAdapter()
        await slack.connect(ChannelCredentials(bot_token=settings.slack_bot_token))
        channel_adapters["slack"] = slack
    return RoutingService(channel_adapters=channel_adapters, settings=settings)
