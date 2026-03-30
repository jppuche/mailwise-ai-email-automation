"""Fixtures for auth integration tests.

Principle: mock external services, NEVER mock the DB in integration tests.
The database and Redis ARE the systems under test here.

Database setup mirrors tests/models/conftest.py:
  - NullPool to prevent DDL deadlocks.
  - migrated_db_module runs alembic upgrade head once per module.
  - Test engine overrides app.dependency_overrides[get_async_db].

Redis teardown:
  - reset_redis_singleton resets the global before each test to prevent
    event loop mismatch when module-scoped fixtures create connections.

Usage:
  pytest tests/integration/ --run-integration
"""

import uuid
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from alembic.config import Config as AlembicConfig
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from alembic import command as alembic_command
from src.api.main import app
from src.core.config import get_settings
from src.core.database import get_async_db
from src.core.security import hash_password
from src.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_alembic_config() -> AlembicConfig:
    """Build an AlembicConfig pointing at the test database."""
    settings = get_settings()
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.database_url_sync)
    return cfg


# ---------------------------------------------------------------------------
# DB migration — module scoped, upgrade only (no teardown downgrade).
# PostgreSQL blocks DDL while sessions hold connections.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def migrated_db_module() -> Generator[None, None, None]:
    """Apply alembic migrations once for the module, upgrade only.

    No teardown downgrade: NullPool sessions still held by SQLAlchemy pool
    internals block PostgreSQL DDL during downgrade on Windows.
    """
    cfg = _get_alembic_config()
    alembic_command.upgrade(cfg, "head")
    yield


# ---------------------------------------------------------------------------
# Async test engine + session — uses NullPool, overrides app dependency.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def override_db(migrated_db_module: None) -> AsyncGenerator[None, None]:
    """Override get_async_db dependency with a NullPool test engine.

    Scope: module — one engine per test module.
    NullPool: each session gets a fresh connection, no pooling.
      Prevents DDL deadlocks and ensures isolation between tests.
    """
    settings = get_settings()
    test_async_engine = create_async_engine(
        settings.database_url,
        echo=False,
        poolclass=NullPool,
    )
    TestAsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
        test_async_engine,
        expire_on_commit=False,
    )

    async def override_get_async_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestAsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_async_db] = override_get_async_db
    yield
    app.dependency_overrides.pop(get_async_db, None)
    await test_async_engine.dispose()


# ---------------------------------------------------------------------------
# HTTP client — ASGITransport, no real network calls.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def async_client(override_db: None) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient wired to the FastAPI ASGI app.

    Uses ASGITransport — requests go through FastAPI's full middleware stack
    (CORS, exception handlers, dependency injection) without hitting a real port.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Test user fixtures — real DB inserts, unique usernames per test run.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def admin_user(override_db: None) -> AsyncGenerator[User, None]:
    """Create an active Admin user in the real DB.

    Uses a UUID suffix so multiple test runs don't collide on the
    unique username constraint.
    """
    settings = get_settings()
    test_async_engine = create_async_engine(
        settings.database_url,
        echo=False,
        poolclass=NullPool,
    )
    TestAsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
        test_async_engine,
        expire_on_commit=False,
    )

    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"test_admin_{suffix}",
        password_hash=hash_password("admin_pass_123"),
        role=UserRole.ADMIN,
        is_active=True,
    )

    async with TestAsyncSessionLocal() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)

    yield user

    async with TestAsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
        if db_user is not None:
            await session.delete(db_user)
            await session.commit()

    await test_async_engine.dispose()


@pytest_asyncio.fixture(scope="module")
async def reviewer_user(override_db: None) -> AsyncGenerator[User, None]:
    """Create an active Reviewer user in the real DB."""
    settings = get_settings()
    test_async_engine = create_async_engine(
        settings.database_url,
        echo=False,
        poolclass=NullPool,
    )
    TestAsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
        test_async_engine,
        expire_on_commit=False,
    )

    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"test_reviewer_{suffix}",
        password_hash=hash_password("reviewer_pass_123"),
        role=UserRole.REVIEWER,
        is_active=True,
    )

    async with TestAsyncSessionLocal() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)

    yield user

    async with TestAsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
        if db_user is not None:
            await session.delete(db_user)
            await session.commit()

    await test_async_engine.dispose()


# ---------------------------------------------------------------------------
# Token fixtures — perform a real login against the test app.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def admin_tokens(
    async_client: AsyncClient,
    admin_user: User,
) -> tuple[str, str]:
    """Log in the admin user and return (access_token, refresh_token).

    Performs a real POST /api/v1/auth/login request through the ASGI stack.
    """
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"username": admin_user.username, "password": "admin_pass_123"},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    return data["access_token"], data["refresh_token"]


@pytest_asyncio.fixture(scope="module")
async def reviewer_tokens(
    async_client: AsyncClient,
    reviewer_user: User,
) -> tuple[str, str]:
    """Log in the reviewer user and return (access_token, refresh_token)."""
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"username": reviewer_user.username, "password": "reviewer_pass_123"},
    )
    assert response.status_code == 200, f"Reviewer login failed: {response.text}"
    data = response.json()
    return data["access_token"], data["refresh_token"]


# ---------------------------------------------------------------------------
# Redis cleanup — reset singleton between tests to avoid event loop mismatch.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_redis_singleton() -> Generator[None, None, None]:
    """Reset the Redis singleton before each test.

    Module-scoped fixtures (admin_tokens, reviewer_tokens) create a Redis
    connection on the module event loop. Function-scoped tests run on their
    own event loop. Resetting the global to None forces a fresh connection
    per test, avoiding 'Event loop is closed' errors.

    Data in Redis persists — only the Python connection object is replaced.
    """
    import src.adapters.redis_client as _redis_mod

    _redis_mod._redis_client = None
    yield
    _redis_mod._redis_client = None
