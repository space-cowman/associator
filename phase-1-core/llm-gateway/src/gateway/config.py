"""Gateway settings from environment variables."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    groq_api_key: SecretStr | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    platform_model: str = "openai/gpt-oss-120b"
    platform_reasoning_effort: str | None = "low"
    platform_small_model: str = "qwen/qwen3.8-27b"
    platform_fallback_model: str | None = "openai/gpt-oss-20b"
    aws_region: str = "ap-south-1"
    user_keys_kms_arn: str | None = None
    docs_enabled: bool = False
    safety_url: str = "http://safety.ai.svc.cluster.local:8002"
    langsmith_api_key: SecretStr | None = None
    langsmith_endpoint: str = "https://apac.api.smith.langchain.com"
    langsmith_project: str = "associator-drafts"


@lru_cache
def get_settings() -> Settings:
    """Read the settings once from the environment."""
    return Settings()
