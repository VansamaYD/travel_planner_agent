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
    config_root: Path = Field(
        default=Path("config"),
        validation_alias=AliasChoices("TRAVEL_CONFIG_ROOT", "CONFIG_ROOT"),
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
    deepseek_api_key: SecretStr | None = Field(default=None, validation_alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com", validation_alias="DEEPSEEK_BASE_URL"
    )
    deepseek_model: str = Field(default="", validation_alias="DEEPSEEK_MODEL")
    model_test_timeout_seconds: int = Field(
        default=120, ge=10, le=300, validation_alias="MODEL_TEST_TIMEOUT_SECONDS"
    )
    model_planning_max_output_tokens: int = Field(
        default=8192, ge=512, le=32768, validation_alias="MODEL_PLANNING_MAX_OUTPUT_TOKENS"
    )
    vision_analysis_enabled: bool = Field(default=False, validation_alias="VISION_ANALYSIS_ENABLED")
    deepseek_vision_model: str = Field(
        default="deepseek-v4-flash-vision-exp", validation_alias="DEEPSEEK_VISION_MODEL"
    )
    vision_timeout_seconds: int = Field(
        default=60, ge=10, le=120, validation_alias="VISION_TIMEOUT_SECONDS"
    )
    amap_web_service_key: SecretStr | None = Field(
        default=None, validation_alias="AMAP_WEB_SERVICE_KEY"
    )
    amap_js_api_key: SecretStr | None = Field(default=None, validation_alias="AMAP_JS_API_KEY")
    amap_js_security_key: SecretStr | None = Field(
        default=None, validation_alias="AMAP_JS_SECURITY_KEY"
    )
    baidu_map_server_ak: SecretStr | None = Field(
        default=None, validation_alias="BAIDU_MAP_SERVER_AK"
    )
    baidu_map_server_sk: SecretStr | None = Field(
        default=None, validation_alias="BAIDU_MAP_SERVER_SK"
    )
    baidu_map_js_ak: SecretStr | None = Field(default=None, validation_alias="BAIDU_MAP_JS_AK")
    qweather_api_host: str = Field(default="", validation_alias="QWEATHER_API_HOST")
    qweather_api_key: SecretStr | None = Field(default=None, validation_alias="QWEATHER_API_KEY")
    external_tool_timeout_seconds: int = Field(
        default=15, ge=3, le=60, validation_alias="EXTERNAL_TOOL_TIMEOUT_SECONDS"
    )
    map_cache_ttl_seconds: int = Field(
        default=604800, ge=300, le=2592000, validation_alias="MAP_CACHE_TTL_SECONDS"
    )
    route_cache_ttl_seconds: int = Field(
        default=1800, ge=60, le=86400, validation_alias="ROUTE_CACHE_TTL_SECONDS"
    )
    weather_cache_ttl_seconds: int = Field(
        default=7200, ge=300, le=21600, validation_alias="WEATHER_CACHE_TTL_SECONDS"
    )
    external_cache_stale_seconds: int = Field(
        default=604800, ge=0, le=2592000, validation_alias="EXTERNAL_CACHE_STALE_SECONDS"
    )
    xhs_research_enabled: bool = Field(default=False, validation_alias="XHS_RESEARCH_ENABLED")
    xhs_mcp_endpoint: str = Field(
        default="http://xhs-browser-worker:18060/mcp", validation_alias="XHS_MCP_ENDPOINT"
    )
    xhs_search_timeout_seconds: int = Field(
        default=45, ge=10, le=120, validation_alias="XHS_SEARCH_TIMEOUT_SECONDS"
    )
    xhs_search_cache_ttl_seconds: int = Field(
        default=21600, ge=300, le=604800, validation_alias="XHS_SEARCH_CACHE_TTL_SECONDS"
    )
    xhs_detail_cache_ttl_seconds: int = Field(
        default=86400, ge=1800, le=2592000, validation_alias="XHS_DETAIL_CACHE_TTL_SECONDS"
    )
    xhs_max_results_per_query: int = Field(
        default=8, ge=1, le=10, validation_alias="XHS_MAX_RESULTS_PER_QUERY"
    )
    smtp_host: str = Field(default="", validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=465, ge=1, le=65535, validation_alias="SMTP_PORT")
    smtp_username: str = Field(default="", validation_alias="SMTP_USERNAME")
    smtp_password: SecretStr | None = Field(default=None, validation_alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, validation_alias="SMTP_USE_TLS")
    smtp_from_address: str = Field(default="", validation_alias="SMTP_FROM_ADDRESS")

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
        self.config_root.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
