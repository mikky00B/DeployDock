import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AppBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    repository_url: str = Field(min_length=1, max_length=500)
    branch: str = Field(default="main", min_length=1, max_length=120)
    app_path: str = Field(min_length=1, max_length=500)
    service_name: str | None = Field(default=None, min_length=1, max_length=120)
    deploy_command: str = Field(min_length=1)
    restart_command: str | None = Field(default=None, min_length=1)
    healthcheck_url: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("deploy_command")
    @classmethod
    def deploy_command_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Deploy command must not be blank")
        return value

    @field_validator("restart_command")
    @classmethod
    def restart_command_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Restart command must not be blank")
        return value


class AppCreate(AppBase):
    server_id: uuid.UUID


class AppUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    server_id: uuid.UUID | None = None
    repository_url: str | None = Field(default=None, min_length=1, max_length=500)
    branch: str | None = Field(default=None, min_length=1, max_length=120)
    app_path: str | None = Field(default=None, min_length=1, max_length=500)
    service_name: str | None = Field(default=None, min_length=1, max_length=120)
    deploy_command: str | None = Field(default=None, min_length=1)
    restart_command: str | None = Field(default=None, min_length=1)
    healthcheck_url: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("deploy_command")
    @classmethod
    def deploy_command_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Deploy command must not be blank")
        return value

    @field_validator("restart_command")
    @classmethod
    def restart_command_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Restart command must not be blank")
        return value


class AppRead(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    server_id: uuid.UUID
    name: str
    repository_url: str
    branch: str
    app_path: str
    service_name: str | None
    deploy_command: str
    restart_command: str | None
    healthcheck_url: str | None
    current_commit: str | None
    last_successful_commit: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppServiceStatusRead(BaseModel):
    service_name: str | None
    status: str


class AppServiceRestartRead(BaseModel):
    service_name: str | None
    success: bool
    exit_code: int
    message: str


class AppServiceLogsRead(BaseModel):
    service_name: str | None
    logs: str
