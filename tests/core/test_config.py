import pytest
from pydantic import ValidationError

from src.core.config import Settings


class TestSettingsLoadsFromEnv:
    def test_loads_required_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host/db")
        monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql+psycopg2://u:p@host/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
        settings = Settings(_env_file=None)
        assert settings.database_url == "postgresql+asyncpg://u:p@host/db"
        assert settings.database_url_sync == "postgresql+psycopg2://u:p@host/db"
        assert settings.jwt_secret_key == "test-secret"

    def test_loads_optional_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host/db")
        monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql+psycopg2://u:p@host/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
        monkeypatch.setenv("REDIS_URL", "redis://custom:6380/1")
        settings = Settings(_env_file=None)
        assert settings.redis_url == "redis://custom:6380/1"


class TestSettingsDefaults:
    @pytest.fixture()
    def settings(self, monkeypatch: pytest.MonkeyPatch) -> Settings:
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host/db")
        monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql+psycopg2://u:p@host/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
        return Settings(_env_file=None)

    def test_redis_url_default(self, settings: Settings) -> None:
        assert settings.redis_url == "redis://redis:6379/0"

    def test_jwt_defaults(self, settings: Settings) -> None:
        assert settings.jwt_algorithm == "HS256"
        assert settings.jwt_access_ttl_minutes == 15
        assert settings.jwt_refresh_ttl_days == 7

    def test_security_defaults(self, settings: Settings) -> None:
        assert settings.bcrypt_rounds == 12
        assert settings.cors_origins == ["http://localhost:5173"]

    def test_pipeline_defaults(self, settings: Settings) -> None:
        assert settings.polling_interval_seconds == 300
        assert settings.ingestion_batch_size == 50
        assert settings.max_body_length == 4000
        assert settings.snippet_length == 200
        assert settings.data_retention_days == 90

    def test_llm_defaults(self, settings: Settings) -> None:
        assert settings.llm_model_classify == "gpt-4o-mini"
        assert settings.llm_model_draft == "gpt-4o"
        assert settings.llm_temperature_classify == pytest.approx(0.1)
        assert settings.llm_temperature_draft == pytest.approx(0.7)

    def test_celery_defaults(self, settings: Settings) -> None:
        assert settings.celery_max_retries == 3
        assert settings.celery_backoff_base == 60


class TestSettingsValidation:
    def test_missing_database_url_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
        with pytest.raises(ValidationError):
            Settings(_env_file=None)

    def test_missing_jwt_secret_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host/db")
        monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql+psycopg2://u:p@host/db")
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)
