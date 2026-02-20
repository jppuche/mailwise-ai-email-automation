"""Alembic environment configuration for mailwise.

Uses the sync database URL (psycopg2) for migrations. Alembic is synchronous —
using the async driver adds complexity with no benefit for migration execution.

The DB URL is sourced from Settings (not alembic.ini) to keep .env as the
single source of truth.

IMPORTANT: We do NOT import Base/models here for regular migrations.
Importing ORM models registers enum types with create_type=True in SQLAlchemy's
global type cache, which conflicts with hand-written migrations that create
enums explicitly. For autogenerate (future), add a --autogenerate flag that
conditionally imports Base and sets target_metadata.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from src.core.config import get_settings

# Alembic Config object — provides access to values within alembic.ini
alembic_config = context.config

# Configure Python logging from alembic.ini [loggers] section
if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

# Override sqlalchemy.url from Settings — never hardcode in alembic.ini (D14)
_settings = get_settings()
alembic_config.set_main_option("sqlalchemy.url", _settings.database_url_sync)

# target_metadata is None for hand-written migrations.
# For autogenerate, import Base from src.models and set:
#   from src.models import Base
#   target_metadata = Base.metadata
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection).

    Generates SQL statements to stdout. Useful for review before applying
    migrations in production, or when a live DB is not available.
    """
    url = alembic_config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (live DB connection).

    Uses NullPool — migrations are short-lived, pooling adds no benefit.
    """
    connectable = create_engine(
        _settings.database_url_sync,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
