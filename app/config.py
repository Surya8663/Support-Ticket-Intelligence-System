from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Single source of configuration. Thresholds and paths live here, not in logic files."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
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
        "http://localhost:4173,http://127.0.0.1:4173,"
        "http://localhost:8501,http://127.0.0.1:8501"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @model_validator(mode="after")
    def resolve_data_paths(self) -> "Settings":
        """Relative CSV/DB paths are repo-root based, not process-cwd based."""
        if not self.csv_path.is_absolute():
            self.csv_path = (REPO_ROOT / self.csv_path).resolve()
        if not self.db_path.is_absolute():
            self.db_path = (REPO_ROOT / self.db_path).resolve()
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
