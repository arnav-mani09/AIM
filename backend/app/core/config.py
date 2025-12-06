from pydantic_settings import BaseSettings
from functools import lru_cache


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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        protected_namespaces = ("settings_",)


@lru_cache
def get_settings() -> Settings:
    return Settings()
