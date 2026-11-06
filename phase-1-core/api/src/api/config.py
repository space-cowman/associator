"""API settings from environment variables."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = "postgresql+psycopg://platform_v2_app@127.0.0.1:15432/platform_v2"
    redis_url: str = "redis://platform_v2_app@127.0.0.1:16379/0"
    redis_password: SecretStr | None = None
    jwt_signing_key: SecretStr | None = None
    llm_gateway_url: str = "http://127.0.0.1:4000"
    safety_url: str = "http://127.0.0.1:8002"
    orchestrator_url: str | None = None
    aws_region: str = "ap-south-1"
    user_keys_kms_arn: str | None = None
    attachments_bucket: str | None = None
    free_models_only: bool = True
    activity_metrics: bool = False
    docs_enabled: bool = False
    public_url: str = "https://associator.space"
    github_client_id: str | None = None
    github_client_secret: SecretStr | None = None
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    identity_pepper: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    """Read the settings once from the environment."""
    return Settings()
