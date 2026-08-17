from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/insights.db"
    max_upload_bytes: int = 200 * 1024 * 1024
    max_csv_rows: int = 100_000
    max_dataset_rows: int = 2_000_000
    upload_dir: str = "./data/uploads"
    qa_cache_dir: str = "./data/cache"
    qa_max_result_rows: int = 100
    qa_query_timeout_seconds: int = 30
    qa_vector_max_rows: int = 50_000
    duckdb_memory_limit: str = "2GB"
    duckdb_threads: int = 4
    preview_row_limit: int = 100
    llm_api_key: str | None = None
    llm_base_url: str = "https://llm.maqsoftware.net/v1"
    llm_default_model: str = "qwen-3.6-27b"
    llm_fallback_model: str = "gemma-4-31b"
    cors_origins: str = "*"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
