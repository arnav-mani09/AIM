import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    project_name: str = "AIM Platform API"
    api_v1_prefix: str = "/api/v1"
    secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    database_url: str

    model_gateway_url: str | None = None
    model_gateway_token: str | None = None
    frontend_base_url: str = "http://localhost:3000"
    email_from_address: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str | None = None
    media_root: str = "storage/uploads"
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket: str = "aim-film"
    # Modal reads its own credentials (~/.modal.toml locally, MODAL_TOKEN_ID /
    # MODAL_TOKEN_SECRET on Render).
    modal_film_app: str = "aim-film"
    sentry_dsn: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        protected_namespaces = ("settings_",)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def deployment_environment() -> str:
    """Render sets RENDER=true; anywhere else is local development."""
    return "production" if os.environ.get("RENDER") else "development"
