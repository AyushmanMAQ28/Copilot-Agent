from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/insights.db"
    max_upload_bytes: int = 50 * 1024 * 1024
    max_csv_rows: int = 100_000
    llm_api_key: str | None = None
    llm_base_url: str = "https://llm.maqsoftware.net/v1"
    llm_default_model: str = "qwen-3.6-27b"
    llm_fallback_model: str = "gemma-4-31b"
    cors_origins: str = "*"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
