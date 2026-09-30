import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.environment import DomainStatus, SSLStatus

ENVIRONMENT_NAME_PATTERN = r"^[a-z][a-z0-9-]{0,118}$"


class EnvironmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    server_id: uuid.UUID
    auto_deploy: bool = True
    health_path: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("name")
    @classmethod
    def name_is_a_slug(cls, value: str) -> str:
        import re

        if not re.match(ENVIRONMENT_NAME_PATTERN, value):
            raise ValueError("Environment name must be a lowercase slug (a-z, 0-9, -)")
        return value


class EnvironmentRead(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    server_id: uuid.UUID
    name: str
    auto_deploy: bool
    health_path: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VariableSet(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    value: str = Field(min_length=1)


class VariableRead(BaseModel):
    key: str
    # Masked reads (spec §38): the plaintext never leaves the control plane.
    set: bool = True


class DomainCreate(BaseModel):
    hostname: str = Field(min_length=3, max_length=255)

    @field_validator("hostname")
    @classmethod
    def hostname_is_lowercased(cls, value: str) -> str:
        return value.strip().lower()


class DomainRead(BaseModel):
    id: uuid.UUID
    environment_id: uuid.UUID
    hostname: str
    status: DomainStatus
    ssl_status: SSLStatus
    last_verification_error: str | None
    verified_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DomainVerifyRead(BaseModel):
    verified: bool
    message: str
    expected_ip: str | None = None
    resolved_ips: list[str] = []
