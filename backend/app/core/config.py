from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    database_url: str = Field(
        default="postgresql+asyncpg://deploydock:deploydock@localhost:5432/deploydock",
        alias="DATABASE_URL",
    )
    secret_key: str = Field(default="change-me", alias="SECRET_KEY")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    encryption_key: str = Field(default="change-me-32-byte-key", alias="ENCRYPTION_KEY")
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8")

    @field_validator("app_env")
    @classmethod
    def normalize_app_env(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if not self.is_production:
            return self

        if self.secret_key == "change-me" or len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must be changed to a strong value in production")

        if self.encryption_key in {"change-me", "change-me-32-byte-key"} or len(self.encryption_key) < 32:
            raise ValueError("ENCRYPTION_KEY must be changed to a stable strong value in production")

        if any(origin == "*" for origin in self.cors_origin_list):
            raise ValueError("CORS_ORIGINS must not include '*' in production")

        local_origins = ("localhost", "127.0.0.1", "0.0.0.0")
        if any(any(local_origin in origin for local_origin in local_origins) for origin in self.cors_origin_list):
            raise ValueError("CORS_ORIGINS must point at the production frontend in production")

        return self

    @property
    def is_production(self) -> bool:
        return self.app_env in {"production", "prod"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
