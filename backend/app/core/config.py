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
    encryption_key_id: str = Field(default="v1", alias="ENCRYPTION_KEY_ID")
    encryption_keys_retired: str = Field(default="", alias="ENCRYPTION_KEYS_RETIRED")
    cors_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173", alias="CORS_ORIGINS")

    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    login_max_attempts: int = Field(default=5, alias="LOGIN_MAX_ATTEMPTS")
    login_window_seconds: int = Field(default=60, alias="LOGIN_WINDOW_SECONDS")

    deploy_timeout_seconds: int = Field(default=900, alias="DEPLOY_TIMEOUT_SECONDS")
    rollback_timeout_seconds: int = Field(default=300, alias="ROLLBACK_TIMEOUT_SECONDS")
    orphan_deployment_timeout_seconds: int = Field(
        default=3600,
        alias="ORPHAN_DEPLOYMENT_TIMEOUT_SECONDS",
    )

    heartbeat_interval_seconds: int = Field(default=30, alias="HEARTBEAT_INTERVAL_SECONDS")
    agent_registration_token_ttl_seconds: int = Field(
        default=900,
        alias="AGENT_REGISTRATION_TOKEN_TTL_SECONDS",
    )
    agent_offline_after_seconds: int = Field(default=90, alias="AGENT_OFFLINE_AFTER_SECONDS")
    # A claimed command older than this is assumed lost (agent died mid-deploy):
    # the sweep fails the command and its deployment so the app is not blocked.
    # Must exceed the longest legitimate deploy (DEPLOY_TIMEOUT_SECONDS).
    agent_command_lease_seconds: int = Field(default=1800, alias="AGENT_COMMAND_LEASE_SECONDS")
    agent_reclaim_sweep_seconds: int = Field(default=300, alias="AGENT_RECLAIM_SWEEP_SECONDS")
    # Trust X-Forwarded-For for client IP resolution (rate limiting, audit).
    # Only enable behind a reverse proxy you control, otherwise clients can
    # spoof their address.
    trust_proxy_headers: bool = Field(default=False, alias="TRUST_PROXY_HEADERS")
    register_max_attempts: int = Field(default=10, alias="REGISTER_MAX_ATTEMPTS")
    register_window_seconds: int = Field(default=3600, alias="REGISTER_WINDOW_SECONDS")

    # Email (SMTP). With smtp_host unset, email is disabled: signup codes are
    # skipped, accounts are created active, and notifications are dropped.
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    email_from: str = Field(default="", alias="EMAIL_FROM")
    email_from_name: str = Field(default="DeployDock", alias="EMAIL_FROM_NAME")
    app_public_url: str = Field(default="http://127.0.0.1:5173", alias="APP_PUBLIC_URL")
    # When true, a fresh account cannot log in until it verifies the emailed
    # 6-digit code. Default off so local development and tests work without SMTP.
    require_email_verification: bool = Field(
        default=False,
        alias="REQUIRE_EMAIL_VERIFICATION",
    )
    email_code_ttl_seconds: int = Field(default=900, alias="EMAIL_CODE_TTL_SECONDS")
    email_code_max_attempts: int = Field(default=5, alias="EMAIL_CODE_MAX_ATTEMPTS")
    email_notifications_enabled: bool = Field(
        default=True,
        alias="EMAIL_NOTIFICATIONS_ENABLED",
    )

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8")

    @field_validator("app_env")
    @classmethod
    def normalize_app_env(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("encryption_key_id")
    @classmethod
    def validate_encryption_key_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("ENCRYPTION_KEY_ID must not be empty")
        if ":" in value:
            raise ValueError("ENCRYPTION_KEY_ID must not contain ':'")
        return value

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        # Parsed eagerly so a malformed retired-key list fails at boot, not at decrypt time.
        self.retired_encryption_keys  # noqa: B018

        if not self.is_production:
            return self

        if self.secret_key == "change-me" or len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must be changed to a strong value in production")

        weak_encryption_keys = {"change-me", "change-me-32-byte-key"}
        if self.encryption_key in weak_encryption_keys or len(self.encryption_key) < 32:
            raise ValueError("ENCRYPTION_KEY must be changed to a stable strong value in production")

        if any(origin == "*" for origin in self.cors_origin_list):
            raise ValueError("CORS_ORIGINS must not include '*' in production")

        local_origins = ("localhost", "127.0.0.1", "0.0.0.0")
        if any(
            any(local_origin in origin for local_origin in local_origins)
            for origin in self.cors_origin_list
        ):
            raise ValueError("CORS_ORIGINS must point at the production frontend in production")

        return self

    @property
    def is_production(self) -> bool:
        return self.app_env in {"production", "prod"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def retired_encryption_keys(self) -> dict[str, str]:
        """Previously active encryption keys, still accepted for decryption.

        Format: ``ENCRYPTION_KEYS_RETIRED=v0:old-secret,legacy:older-secret``
        """
        retired: dict[str, str] = {}
        for entry in self.encryption_keys_retired.split(","):
            entry = entry.strip()
            if not entry:
                continue
            key_id, separator, secret = entry.partition(":")
            if not separator or not key_id.strip() or not secret.strip():
                raise ValueError(
                    "ENCRYPTION_KEYS_RETIRED entries must look like 'key_id:secret', comma-separated"
                )
            retired[key_id.strip()] = secret.strip()
        return retired


@lru_cache
def get_settings() -> Settings:
    return Settings()
