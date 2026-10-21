from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    http_timeout_seconds: float = 15.0
    # Identify yourself honestly. Sites can contact you instead of blocking you.
    http_user_agent: str = "MarketLensAI/0.1 (portfolio project; contact: you@example.com)"


@lru_cache
def get_settings() -> Settings:
    return Settings()