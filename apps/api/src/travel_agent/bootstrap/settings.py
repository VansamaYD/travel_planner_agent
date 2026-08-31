from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed runtime settings; existing repository environment names remain supported."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Travel Planner Agent"
    app_version: str = "0.1.0"
    app_env: Literal["development", "test", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENV", "TRAVEL_APP_ENV"),
    )
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("APP_LOG_LEVEL", "TRAVEL_LOG_LEVEL"),
    )
    timezone: str = Field(
        default="Asia/Shanghai",
        validation_alias=AliasChoices("APP_TIMEZONE", "TRAVEL_TIMEZONE"),
    )
    data_root: Path = Field(
        default=Path("data"),
        validation_alias=AliasChoices("TRAVEL_DATA_ROOT", "DATA_ROOT"),
    )
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_URL", "TRAVEL_DATABASE_URL"),
    )
    app_master_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("APP_MASTER_KEY", "TRAVEL_APP_MASTER_KEY"),
    )
    session_lifetime_days: int = Field(
        default=7,
        ge=1,
        le=30,
        validation_alias=AliasChoices("SESSION_LIFETIME_DAYS", "TRAVEL_SESSION_LIFETIME_DAYS"),
    )
    session_cookie_name: str = Field(
        default="travel_session",
        validation_alias=AliasChoices("SESSION_COOKIE_NAME", "TRAVEL_SESSION_COOKIE_NAME"),
    )

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            if self.database_url.startswith("sqlite:///"):
                return self.database_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
            return self.database_url
        db_path = (self.data_root / "db" / "travel_agent.db").resolve()
        return f"sqlite+aiosqlite:///{db_path}"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def ensure_runtime_directories(self) -> None:
        for child in ("db", "files", "exports", "cache", "tmp"):
            (self.data_root / child).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
