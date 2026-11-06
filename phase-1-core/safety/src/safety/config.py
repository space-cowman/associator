"""Safety settings from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    docs_enabled: bool = False
    package_lookup: bool = True
    package_lookup_timeout_seconds: float = 3.0


@lru_cache
def get_settings() -> Settings:
    """Read the settings once from the environment."""
    return Settings()
