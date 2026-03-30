import os

# Set required env vars for tests — avoids dependency on .env file.
# These run before any test module imports Settings.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://mailwise:password@localhost:5432/mailwise"
)
os.environ.setdefault(
    "DATABASE_URL_SYNC", "postgresql+psycopg2://mailwise:password@localhost:5432/mailwise"
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
