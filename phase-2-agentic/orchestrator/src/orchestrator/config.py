"""Orchestrator settings from environment variables."""

import os
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

for _flag in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
    os.environ[_flag] = "false"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    gateway_url: str = "http://llm-gateway.ai.svc.cluster.local:4000"
    gateway_timeout_seconds: float = 90
    postgres_host: str = "postgres.data.svc.cluster.local"
    postgres_port: int = 5432
    postgres_db: str = "platform_v2"
    postgres_user: str = "platform_v2_orchestrator"
    postgres_password: SecretStr | None = None
    run_retention_days: int = 7
    docs_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    """Read the settings once from the environment."""
    return Settings()
