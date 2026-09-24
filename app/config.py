from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of configuration. Thresholds and paths live here, not in logic files."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    csv_path: Path = Path("data/support_tickets.csv")
    db_path: Path = Path("data/tickets.db")
    iqr_multiplier: float = 1.5
    zscore_threshold: float = 3.0
    sla_breach_hours: float = 24.0
    iqr_group_by_category: bool = True
    query_result_row_cap: int = 50
    groq_timeout_seconds: float = 30.0
    groq_max_retries: int = 2
    sql_timeout_seconds: float = 3.0
    sql_progress_check_every: int = 10_000
    sql_max_joins: int = 2
    api_token: str = ""
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173"
    )
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
