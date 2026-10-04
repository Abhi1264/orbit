from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = "change-me-in-production-32-chars-min"
    session_ttl_hours: int = 72

    database_url: str = "postgresql+psycopg://probelens:probelens@localhost:5432/probelens"

    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_database: str = "probelens"
    clickhouse_user: str = "probelens"
    clickhouse_password: str = "probelens"
    clickhouse_readonly_user: str = "probelens_ro"
    clickhouse_readonly_password: str = "probelens_ro"

    redis_url: str = "redis://localhost:6379/0"
    analytics_cache_ttl_seconds: int = 300

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_max_tool_steps: int = Field(default=10, ge=1, le=25)

    # Server-side only; never sent to browsers.
    amplitude_api_key: str = ""
    amplitude_server_zone: Literal["US", "EU"] = "US"

    metabase_url: str = ""
    metabase_site_url: str = ""
    # Used only by the BI provisioning step, never by the API.
    metabase_admin_email: str = ""
    metabase_admin_password: str = ""

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def amplitude_enabled(self) -> bool:
        return bool(self.amplitude_api_key)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
