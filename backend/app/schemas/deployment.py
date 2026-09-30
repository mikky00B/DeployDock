import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.deployment import DeploymentKind, DeploymentStatus
from app.schemas.deployment_log import DeploymentLogRead


class DeploymentRead(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    app_id: uuid.UUID
    server_id: uuid.UUID
    status: DeploymentStatus
    kind: DeploymentKind
    commit_sha: str | None
    previous_commit_sha: str | None
    commit_message: str | None = None
    started_at: datetime | None
    finished_at: datetime | None
    duration_seconds: int | None
    triggered_by: str | None
    exit_code: int | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeploymentDetailRead(DeploymentRead):
    logs: list[DeploymentLogRead] = []
    # Health-check result reported by the agent engine (spec §18).
    healthcheck_url: str | None = None
    healthcheck_status_code: int | None = None
    healthcheck_ok: bool | None = None
    healthcheck_error: str | None = None
