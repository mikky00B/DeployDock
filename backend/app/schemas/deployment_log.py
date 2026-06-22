import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.deployment_log import DeploymentLogStream


class DeploymentLogRead(BaseModel):
    id: uuid.UUID
    deployment_id: uuid.UUID
    stream: DeploymentLogStream
    line: str
    sequence: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
