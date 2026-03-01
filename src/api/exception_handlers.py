"""Global exception handlers — domain exceptions to HTTP status codes.

Architecture constraint: routers have ZERO try/except. All domain
exceptions propagate here. Only exception: health.py._check_adapter.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse

from src.api.schemas.common import ErrorResponse
from src.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    CategoryNotFoundError,
    DuplicateEmailError,
    DuplicateResourceError,
    InvalidStateTransitionError,
    NotFoundError,
)


async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    """NotFoundError -> 404."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(error="not_found", message=str(exc)).model_dump(),
    )


async def category_not_found_handler(request: Request, exc: CategoryNotFoundError) -> JSONResponse:
    """CategoryNotFoundError -> 404."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(error="category_not_found", message=str(exc)).model_dump(),
    )


async def invalid_state_handler(request: Request, exc: InvalidStateTransitionError) -> JSONResponse:
    """InvalidStateTransitionError -> 409."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=ErrorResponse(error="invalid_state_transition", message=str(exc)).model_dump(),
    )


async def duplicate_email_handler(request: Request, exc: DuplicateEmailError) -> JSONResponse:
    """DuplicateEmailError -> 409."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=ErrorResponse(error="duplicate_email", message=str(exc)).model_dump(),
    )


async def duplicate_resource_handler(request: Request, exc: DuplicateResourceError) -> JSONResponse:
    """DuplicateResourceError -> 409."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=ErrorResponse(error="duplicate_resource", message=str(exc)).model_dump(),
    )


async def authentication_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    """AuthenticationError -> 401."""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=ErrorResponse(error="unauthorized", message=str(exc)).model_dump(),
    )


async def authorization_error_handler(request: Request, exc: AuthorizationError) -> JSONResponse:
    """AuthorizationError -> 403."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=ErrorResponse(error="forbidden", message=str(exc)).model_dump(),
    )
