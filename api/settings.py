from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    tool_provider: Literal["simulator", "live"] = "simulator"
    kubernetes_namespace: str = Field(default="sentinel-demo", pattern=r"^[a-z0-9-]+$")
    kubectl_context: str = ""
    prometheus_url: str = "http://localhost:9090"
    tempo_url: str = ""
    git_repository_path: str = "."
    github_repository: str = ""
    github_token: str = ""
    otlp_endpoint: str = ""
    max_runtime_seconds: int = Field(default=300, ge=1)
    max_model_tokens: int = Field(default=60_000, ge=1)
    max_tool_calls: int = Field(default=40, ge=1)
    max_subagents: int = Field(default=8, ge=1)
    max_identical_tool_calls: int = Field(default=3, ge=1)
    max_cost_usd: float = Field(default=1.0, ge=0.0)
    worker_lease_seconds: float = Field(default=60.0, gt=0.0)
    worker_poll_seconds: float = Field(default=1.0, gt=0.0)
    worker_max_attempts: int = Field(default=3, ge=1, le=20)

    @property
    def resolved_git_repository_path(self) -> Path:
        return Path(self.git_repository_path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
