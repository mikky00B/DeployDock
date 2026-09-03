import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.server import ServerAuthType, ServerStatus


class ServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=120)
    private_key: str | None = Field(default=None, min_length=1)


class ServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, min_length=1, max_length=120)
    private_key: str | None = Field(default=None, min_length=1)


class ServerRead(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    host: str
    port: int
    username: str
    auth_type: ServerAuthType
    public_ssh_key: str | None
    private_key_fingerprint: str | None
    known_host_key_fingerprint: str | None
    known_host_key_pinned_at: datetime | None
    status: ServerStatus
    last_connection_check_at: datetime | None
    last_connection_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ServerConnectionTestRead(BaseModel):
    success: bool
    status: ServerStatus
    message: str
    host_key_fingerprint: str | None = None


class ServerHostKeyRead(BaseModel):
    fingerprint: str
    algorithm: str
    previous_fingerprint: str | None = None
    message: str
