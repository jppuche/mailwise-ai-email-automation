"""FastAPI application — entry point.

Registers routers and middleware. Thin layer — all logic in services/adapters.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.adapters.redis_client import close_redis
from src.api.routers.auth import router as auth_router
from src.core.config import get_settings
from src.core.exceptions import AuthenticationError, AuthorizationError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
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
@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": str(exc)},
    )


@app.exception_handler(AuthorizationError)
async def authorization_error_handler(request: Request, exc: AuthorizationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": str(exc)},
    )


# --- Routers ---
app.include_router(auth_router)


# --- Health check ---
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
