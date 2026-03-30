"""FastAPI application — entry point.

Registers routers and middleware. Thin layer — all logic in services/adapters.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.adapters.redis_client import close_redis
from src.api.exception_handlers import (
    authentication_error_handler,
    authorization_error_handler,
    category_in_use_handler,
    category_not_found_handler,
    duplicate_email_handler,
    duplicate_resource_handler,
    invalid_state_handler,
    not_found_handler,
)
from src.api.routers.analytics import router as analytics_router
from src.api.routers.auth import router as auth_router
from src.api.routers.categories import categories_router, classification_router
from src.api.routers.drafts import router as drafts_router
from src.api.routers.emails import router as emails_router
from src.api.routers.health import router as health_router
from src.api.routers.integrations import router as integrations_router
from src.api.routers.logs import router as logs_router
from src.api.routers.routing_rules import router as routing_rules_router
from src.core.config import get_settings
from src.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    CategoryInUseError,
    CategoryNotFoundError,
    DuplicateEmailError,
    DuplicateResourceError,
    InvalidStateTransitionError,
    NotFoundError,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    import structlog as _structlog

    from src.core.config import get_settings as _get_settings
    from src.core.logging import configure_logging

    _settings = _get_settings()
    configure_logging(
        log_level=_settings.log_level,
        log_format=_settings.log_format,
    )

    _startup_logger = _structlog.get_logger()

    # System prompt length validation: warn when org system prompt is unusually long (>2000 chars)
    if len(_settings.draft_org_system_prompt) > 2000:
        _startup_logger.warning(
            "draft_org_system_prompt_long",
            length=len(_settings.draft_org_system_prompt),
        )

    yield
    await close_redis()


app = FastAPI(title="mailwise", version="0.1.0", lifespan=lifespan)

# --- CORS middleware ---
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Exception handlers ---
app.add_exception_handler(AuthenticationError, authentication_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(AuthorizationError, authorization_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(NotFoundError, not_found_handler)  # type: ignore[arg-type]
app.add_exception_handler(CategoryNotFoundError, category_not_found_handler)  # type: ignore[arg-type]
app.add_exception_handler(InvalidStateTransitionError, invalid_state_handler)  # type: ignore[arg-type]
app.add_exception_handler(DuplicateEmailError, duplicate_email_handler)  # type: ignore[arg-type]
app.add_exception_handler(DuplicateResourceError, duplicate_resource_handler)  # type: ignore[arg-type]
app.add_exception_handler(CategoryInUseError, category_in_use_handler)  # type: ignore[arg-type]

# --- Routers ---
app.include_router(auth_router, prefix="/api/v1")
app.include_router(emails_router, prefix="/api/v1/emails")
app.include_router(routing_rules_router, prefix="/api/v1/routing-rules")
app.include_router(drafts_router, prefix="/api/v1/drafts")
app.include_router(health_router, prefix="/api/v1")
app.include_router(categories_router, prefix="/api/v1/categories")
app.include_router(classification_router, prefix="/api/v1/classification")
app.include_router(integrations_router, prefix="/api/v1/integrations")
app.include_router(analytics_router, prefix="/api/v1/analytics")
app.include_router(logs_router, prefix="/api/v1/logs")
