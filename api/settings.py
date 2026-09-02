from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SENTINEL_", extra="ignore")

    database_url: str = "sqlite:///./sentinel.db"
    env: str = "development"
    api_token: str = "sentinel-local-token"  # noqa: S105 - documented local default
    approval_secret: str = "replace-in-production"  # noqa: S105 - documented local default
    model_provider: str = "deterministic"
    model_name: str = "sentinel-stub-v1"
    otlp_endpoint: str = ""
    max_runtime_seconds: int = Field(default=300, ge=1)
    max_model_tokens: int = Field(default=60_000, ge=1)
    max_tool_calls: int = Field(default=40, ge=1)
    max_subagents: int = Field(default=8, ge=1)
    max_identical_tool_calls: int = Field(default=3, ge=1)
    max_cost_usd: float = Field(default=1.0, ge=0.0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
