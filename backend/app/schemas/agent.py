import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentRegistrationTokenCreate(BaseModel):
    server_id: uuid.UUID | None = None
    ttl_seconds: int = Field(default=900, ge=60, le=3600)


class AgentRegistrationTokenRead(BaseModel):
    token: str
    expires_at: datetime


class AgentRegister(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    agent_version: str | None = Field(default=None, max_length=64)
    os: str | None = Field(default=None, max_length=64)
    arch: str | None = Field(default=None, max_length=32)


class AgentRegisterRead(BaseModel):
    agent_id: uuid.UUID
    agent_token: str
    heartbeat_interval_seconds: int


class AgentHeartbeat(BaseModel):
    agent_version: str | None = Field(default=None, max_length=64)
    metrics: dict | None = None


class AgentHeartbeatRead(BaseModel):
    status: str
    heartbeat_interval_seconds: int
    server_time: datetime


class AgentTokenRotateRead(BaseModel):
    agent_id: uuid.UUID
    agent_token: str
    heartbeat_interval_seconds: int


class AgentRead(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    server_id: uuid.UUID | None
    name: str
    status: str
    agent_version: str | None
    os: str | None
    arch: str | None
    metrics: dict | None
    last_heartbeat_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
