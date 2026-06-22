import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_development_settings_allow_local_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.cors_origin_list == ["http://localhost:5173"]
    assert not settings.is_production


def test_production_rejects_default_secret_key() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY must be changed"):
        Settings(
            APP_ENV="production",
            SECRET_KEY="change-me",
            ENCRYPTION_KEY="a-stable-production-encryption-key",
            CORS_ORIGINS="https://deploydock.example.com",
        )


def test_production_rejects_default_encryption_key() -> None:
    with pytest.raises(ValidationError, match="ENCRYPTION_KEY must be changed"):
        Settings(
            APP_ENV="production",
            SECRET_KEY="a-stable-production-secret-key-value",
            ENCRYPTION_KEY="change-me-32-byte-key",
            CORS_ORIGINS="https://deploydock.example.com",
        )


def test_production_rejects_local_cors_origin() -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS must point"):
        Settings(
            APP_ENV="production",
            SECRET_KEY="a-stable-production-secret-key-value",
            ENCRYPTION_KEY="a-stable-production-encryption-key",
            CORS_ORIGINS="http://localhost:5173",
        )


def test_production_accepts_strong_values() -> None:
    settings = Settings(
        APP_ENV="production",
        SECRET_KEY="a-stable-production-secret-key-value",
        ENCRYPTION_KEY="a-stable-production-encryption-key",
        CORS_ORIGINS="https://deploydock.example.com",
    )

    assert settings.is_production
    assert settings.cors_origin_list == ["https://deploydock.example.com"]
