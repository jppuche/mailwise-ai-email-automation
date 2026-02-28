from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = Field(..., description="PostgreSQL connection URL (async)")
    database_url_sync: str = Field(..., description="PostgreSQL connection URL (sync, for Celery)")

    # Redis
    redis_url: str = Field(default="redis://redis:6379/0")

    # JWT
    jwt_secret_key: str = Field(
        ..., description="Secret key for JWT signing — MUST be set in production"
    )
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_ttl_minutes: int = Field(default=15)
    jwt_refresh_ttl_days: int = Field(default=7)

    # Security
    bcrypt_rounds: int = Field(default=12)
    cors_origins: list[str] = Field(default=["http://localhost:5173"])

    # Pipeline defaults (Cat 8 — all configurable)
    polling_interval_seconds: int = Field(default=300)
    ingestion_batch_size: int = Field(default=50)
    max_body_length: int = Field(default=4000)
    snippet_length: int = Field(default=200)
    data_retention_days: int = Field(default=90)

    # LLM
    llm_model_classify: str = Field(default="gpt-4o-mini")
    llm_model_draft: str = Field(default="gpt-4o")
    llm_temperature_classify: float = Field(default=0.1)
    llm_temperature_draft: float = Field(default=0.7)
    openai_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")
    llm_fallback_model: str = Field(default="gpt-3.5-turbo")
    llm_timeout_seconds: int = Field(default=30)
    llm_classify_max_tokens: int = Field(default=500)
    llm_draft_max_tokens: int = Field(default=2000)
    llm_base_url: str = Field(default="")

    # Celery
    celery_max_retries: int = Field(default=3)
    celery_backoff_base: int = Field(default=60)

    # Gmail OAuth
    gmail_client_id: str = Field(default="")
    gmail_client_secret: str = Field(default="")
    gmail_redirect_uri: str = Field(default="http://localhost:8000/api/v1/auth/gmail/callback")

    # Gmail Adapter (Cat 8: configurable defaults)
    gmail_max_results: int = Field(default=100)
    gmail_credentials_file: str = Field(default="secrets/gmail_credentials.json")
    gmail_token_file: str = Field(default="secrets/gmail_token.json")

    # Slack
    slack_bot_token: str = Field(default="")
    slack_signing_secret: str = Field(default="")

    # Channel Adapter (Cat 8: configurable defaults)
    channel_snippet_length: int = Field(default=150)
    channel_subject_max_length: int = Field(default=100)
    channel_slack_timeout_seconds: int = Field(default=10)
    channel_destinations_page_size: int = Field(default=200)

    # HubSpot
    hubspot_access_token: str = Field(default="")
    hubspot_rate_limit_per_10s: int = Field(default=100)
    hubspot_activity_snippet_length: int = Field(default=200)
    hubspot_auto_create_contacts: bool = Field(default=False)
    hubspot_default_lead_status: str = Field(default="NEW")
    hubspot_api_timeout_seconds: int = Field(default=15)


def get_settings() -> Settings:
    return Settings()
