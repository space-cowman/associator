"""MCP server settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    api_url: str = "http://127.0.0.1:8000"
    allowed_hosts: list[str] = ["127.0.0.1:*", "localhost:*", "mcp-server.app.svc.cluster.local:*"]


@lru_cache
def get_settings() -> Settings:
    """Read the settings once from the environment."""
    return Settings()
