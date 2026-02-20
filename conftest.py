import os

# Set required env vars for tests — avoids dependency on .env file.
# These run before any test module imports Settings.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql+psycopg2://test:test@localhost:5432/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-only")
