import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.deployment import DeploymentKind, DeploymentStatus
from app.models.server import ServerStatus
from app.schemas.audit_log import AuditLogRead


class DashboardSummaryRead(BaseModel):
    total_servers: int
    connected_servers: int
    total_apps: int
    deployed_apps: int
    recent_failures: int
    latest_deployment_status: DeploymentStatus | None


class DashboardServerRead(BaseModel):
    id: uuid.UUID
    name: str
    host: str
    status: ServerStatus

    model_config = ConfigDict(from_attributes=True)


class DashboardAppRead(BaseModel):
    id: uuid.UUID
    name: str
    service_name: str | None
    current_commit: str | None
    last_successful_commit: str | None

    model_config = ConfigDict(from_attributes=True)


class DashboardDeploymentRead(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    status: DeploymentStatus
    kind: DeploymentKind
    commit_sha: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class DashboardRead(BaseModel):
    summary: DashboardSummaryRead
    recent_servers: list[DashboardServerRead]
    recent_apps: list[DashboardAppRead]
    recent_deployments: list[DashboardDeploymentRead]
    recent_audit_logs: list[AuditLogRead]
