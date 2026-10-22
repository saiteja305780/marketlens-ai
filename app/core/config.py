from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    http_timeout_seconds: float = 15.0
    # Identify yourself honestly. Sites can contact you instead of blocking you.
    # e.g. postgresql+psycopg://user:password@localhost:5432/marketlens (set it in .env, never commit it)
    database_url: str | None = None
    # a listing not seen for this many hours is flagged stale in API responses
    stale_after_hours: int = 48
    # shared secret for write/alert endpoints; unset means those endpoints answer 503
    api_key: str | None = None
    # in-process scheduled collection: OFF unless explicitly enabled
    scheduler_enabled: bool = False
    collect_interval_hours: float = Field(default=6.0, ge=1)
    http_user_agent: str = "MarketLensAI/0.1 (portfolio project; contact: you@example.com)"


@lru_cache
def get_settings() -> Settings:
    return Settings()