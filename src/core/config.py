from functools import lru_cache

from pydantic import Field, model_validator
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

    # Pipeline defaults (all configurable)
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
    # Comma-separated allowlist of LLM model names. Empty string means "use configured models".
    llm_allowed_models: str = Field(default="")
    # Parsed frozenset — populated by model_validator, not from env directly.
    llm_allowed_models_set: frozenset[str] = Field(default_factory=frozenset, exclude=True)

    # Ingestion lock (configurable defaults)
    ingestion_lock_ttl_seconds: int = Field(default=300)
    ingestion_lock_key_prefix: str = Field(default="mailwise:ingest:lock")

    # Classification (configurable defaults)
    classify_max_few_shot_examples: int = Field(default=10)
    classify_feedback_snippet_chars: int = Field(default=200)
    classify_internal_domains: str = Field(default="")

    # Celery
    celery_max_retries: int = Field(default=3)
    celery_backoff_base: int = Field(default=60)
    celery_broker_url: str = Field(default="redis://redis:6379/0")
    celery_result_backend: str = Field(default="redis://redis:6379/1")
    celery_result_expires: int = Field(default=3600)

    # Pipeline & Scheduler (configurable defaults)
    pipeline_scheduler_lock_key_prefix: str = Field(default="mailwise:scheduler:lock")
    pipeline_scheduler_lock_ttl_seconds: int = Field(default=300)

    # Gmail OAuth
    gmail_client_id: str = Field(default="")
    gmail_client_secret: str = Field(default="")
    gmail_redirect_uri: str = Field(default="http://localhost:8000/api/v1/auth/gmail/callback")

    # Gmail Adapter (configurable defaults)
    gmail_max_results: int = Field(default=100)
    gmail_credentials_file: str = Field(default="secrets/gmail_credentials.json")
    gmail_token_file: str = Field(default="secrets/gmail_token.json")

    # Slack
    slack_bot_token: str = Field(default="")
    slack_signing_secret: str = Field(default="")

    # Channel Adapter (configurable defaults)
    channel_snippet_length: int = Field(default=150)
    channel_subject_max_length: int = Field(default=100)
    channel_slack_timeout_seconds: int = Field(default=10)
    channel_destinations_page_size: int = Field(default=200)

    # Routing (configurable defaults)
    routing_vip_senders: str = Field(default="")
    routing_dashboard_base_url: str = Field(default="http://localhost:3000")
    routing_snippet_length: int = Field(default=150)

    # HubSpot
    hubspot_access_token: str = Field(default="")
    hubspot_rate_limit_per_10s: int = Field(default=100)
    hubspot_activity_snippet_length: int = Field(default=200)
    hubspot_auto_create_contacts: bool = Field(default=False)
    hubspot_default_lead_status: str = Field(default="NEW")
    hubspot_api_timeout_seconds: int = Field(default=15)

    # CRM Sync (configurable defaults)
    crm_sync_retry_max: int = Field(default=3)
    crm_sync_backoff_base_seconds: int = Field(default=60)

    # Draft Generation (configurable defaults)
    draft_push_to_gmail: bool = Field(default=False)
    draft_org_system_prompt: str = Field(default="", max_length=4096)
    draft_org_tone: str = Field(default="professional")
    draft_org_signature: str = Field(default="")
    draft_org_prohibited_language: str = Field(default="")  # comma-separated
    draft_generation_retry_max: int = Field(default=2)

    # API (configurable defaults)
    api_health_adapter_timeout_ms: int = Field(default=200)
    app_version: str = Field(default="0.1.0")

    # Analytics (configurable defaults)
    analytics_max_date_range_days: int = Field(default=365)
    analytics_csv_chunk_size: int = Field(default=1000)
    analytics_default_timezone: str = Field(default="UTC")

    # Logging
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")

    @model_validator(mode="after")
    def _build_allowed_models_set(self) -> "Settings":
        """Parse llm_allowed_models into a frozenset.

        Empty string defaults to the three configured model names so the
        allowlist is always non-empty after validation (the configured models
        themselves are the default).
        """
        if self.llm_allowed_models.strip():
            parsed: frozenset[str] = frozenset(
                m.strip() for m in self.llm_allowed_models.split(",") if m.strip()
            )
        else:
            parsed = frozenset(
                {self.llm_model_classify, self.llm_model_draft, self.llm_fallback_model}
            )
        self.llm_allowed_models_set = parsed
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
