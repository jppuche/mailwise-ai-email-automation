"""Dual session factories for FastAPI (async) and Celery (sync).

Two separate engine/session pairs are needed because:
- FastAPI uses asyncpg (async driver) with SQLAlchemy async sessions.
- Celery workers use psycopg2 (sync driver) — asyncio event loops are not
  available in Celery worker threads by default.

Engines are built lazily at first use to avoid importing this module in
contexts without a .env file (e.g., during alembic autogenerate or tests
that mock the DB).

D13 (non-atomic stages): Each pipeline stage commits independently.
  - get_async_db() commits at the end of the FastAPI request.
  - Celery tasks use SyncSessionLocal with explicit commits per stage.
    Do NOT rely on a single commit at the end of the full chain.
"""

from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings

# ---------------------------------------------------------------------------
# Engine factories — lazy (called once at first import of the session locals)
# ---------------------------------------------------------------------------


def _build_async_engine() -> AsyncEngine:
    """Build the async SQLAlchemy engine from Settings.

    pool_pre_ping=True: validates connections on checkout, handles DB restarts.
    echo=False: do not log every SQL statement in production.
    """
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )


def _build_sync_engine() -> Engine:
    """Build the sync SQLAlchemy engine from Settings.

    Used by Celery tasks. psycopg2 driver required (DATABASE_URL_SYNC).
    """
    settings = get_settings()
    return create_engine(
        settings.database_url_sync,
        echo=False,
        pool_pre_ping=True,
    )


# ---------------------------------------------------------------------------
# Session factories
# expire_on_commit=False: objects remain usable after commit (important for
# async patterns where re-loading would require another await).
# ---------------------------------------------------------------------------

async_engine = _build_async_engine()
sync_engine = _build_sync_engine()

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    async_engine,
    expire_on_commit=False,
)

SyncSessionLocal: sessionmaker[Session] = sessionmaker(
    sync_engine,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an AsyncSession and commits on success.

    Usage:
        async def endpoint(db: AsyncSession = Depends(get_async_db)):
            ...

    Commits if the handler exits normally; rolls back on any exception.
    The session is always closed — even if commit or rollback fails.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Celery context manager
# ---------------------------------------------------------------------------


@contextmanager
def get_sync_db() -> Generator[Session, None, None]:
    """Context manager that yields a sync Session for Celery tasks.

    Usage:
        with get_sync_db() as db:
            db.add(some_model)
            db.commit()  # commit per pipeline stage (D13)

    Each pipeline stage must call db.commit() explicitly. Do not rely on the
    context manager exit to commit — it only commits if no exception occurred,
    but D13 requires per-stage commits within the task body.
    """
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
