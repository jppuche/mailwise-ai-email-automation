"""Shared fixtures for API unit tests.

Pattern: dependency_overrides for mocked DB and auth.
Tests are NOT integration tests — no real DB or Redis.
All services and adapters are mocked via MagicMock/AsyncMock.
"""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.api.main import app
from src.core.database import get_async_db
from src.models.user import User, UserRole


def _make_mock_user(role: UserRole, user_id: uuid.UUID | None = None) -> MagicMock:
    """Create a MagicMock User with the given role."""
    user = MagicMock(spec=User)
    user.id = user_id or uuid.uuid4()
    user.username = f"test_{role.value}"
    user.role = role
    user.is_active = True
    return user


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock AsyncSession for dependency override."""
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def admin_user() -> MagicMock:
    """Mock Admin User."""
    return _make_mock_user(UserRole.ADMIN)


@pytest.fixture
def reviewer_user() -> MagicMock:
    """Mock Reviewer User."""
    return _make_mock_user(UserRole.REVIEWER)


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient wired to FastAPI via ASGITransport."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_client(
    client: AsyncClient,
    mock_db: AsyncMock,
    admin_user: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    """Client with Admin auth + mock DB."""
    app.dependency_overrides[get_async_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def reviewer_client(
    client: AsyncClient,
    mock_db: AsyncMock,
    reviewer_user: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    """Client with Reviewer auth + mock DB."""
    app.dependency_overrides[get_async_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: reviewer_user
    yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauthenticated_client(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> AsyncGenerator[AsyncClient, None]:
    """Client with mock DB but NO auth override (triggers 401)."""
    app.dependency_overrides[get_async_db] = lambda: mock_db
    app.dependency_overrides.pop(get_current_user, None)
    yield client
    app.dependency_overrides.clear()
