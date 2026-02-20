"""Test fixtures for database-requiring model tests.

These fixtures create real database sessions backed by the PostgreSQL instance
configured in DATABASE_URL_SYNC. They are used by test_categories_seed.py
and test_migrations.py.

Principle: mock external services, NEVER mock the DB in integration tests.
The database IS the system under test for migration and seed data verification.

Usage:
  Tests using these fixtures require a running PostgreSQL instance with
  alembic migrations applied. Mark tests with @pytest.mark.integration to
  signal they need the database.

  Run without DB:  pytest tests/models/test_email_state.py tests/models/test_models_import.py
  Run with DB:     pytest tests/models/ --run-integration
"""

import os
import subprocess
import sys
from collections.abc import Callable, Generator

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from alembic import command as alembic_command
from src.core.config import get_settings


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that require a real PostgreSQL database",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: mark test as requiring a real PostgreSQL database with migrations",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("--run-integration"):
        skip_integration = pytest.mark.skip(
            reason="Requires PostgreSQL — run with --run-integration"
        )
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)


def _get_alembic_config() -> AlembicConfig:
    """Build an AlembicConfig that matches our alembic.ini + env.py settings."""
    settings = get_settings()
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.database_url_sync)
    return cfg


@pytest.fixture(scope="module")
def sync_engine():  # type: ignore[no-untyped-def]
    """Create a synchronous SQLAlchemy engine for the test database.

    Uses DATABASE_URL_SYNC from Settings. NullPool ensures connections are
    truly closed when returned — prevents DDL deadlocks during migration
    teardown on Windows/PostgreSQL.

    Never mocked — the engine connects to a real PostgreSQL instance.
    """
    settings = get_settings()
    engine = create_engine(settings.database_url_sync, echo=False, poolclass=NullPool)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def db_session(sync_engine) -> Generator[Session, None, None]:  # type: ignore[no-untyped-def]
    """Create a SQLAlchemy Session bound to the test database.

    Yields a session that queries the real database. Used to verify
    seed data inserted by Alembic migrations.

    The session is closed after all tests in the module complete.
    """
    SessionFactory = sessionmaker(bind=sync_engine)
    session = SessionFactory()
    yield session
    session.close()


@pytest.fixture(scope="module")
def migrated_db(sync_engine) -> Generator[None, None, None]:  # type: ignore[no-untyped-def]
    """Ensure alembic migrations are applied before tests.

    Upgrade-only — no teardown downgrade. Reason: module-scoped db_session
    holds a connection that blocks PostgreSQL DDL (DROP TABLE) during downgrade.
    Migration lifecycle tests manage their own upgrade/downgrade cycles.

    Scope: module — migrations run once per test module, not per test.
    """
    cfg = _get_alembic_config()
    alembic_command.upgrade(cfg, "head")
    yield


def _run_alembic(command: str, revision: str) -> subprocess.CompletedProcess[str]:
    """Run an alembic command via subprocess and assert it succeeds.

    Used by migration tests that need to test the full CLI path.
    Includes a 60-second timeout to prevent hangs.
    """
    result = subprocess.run(
        [sys.executable, "-m", "alembic", command, revision],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=60,
    )
    assert result.returncode == 0, (
        f"alembic {command} {revision} failed.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    return result


@pytest.fixture()
def alembic_runner() -> Callable[[str, str], subprocess.CompletedProcess[str]]:
    """Return the _run_alembic helper for tests that need direct alembic control."""
    return _run_alembic
