import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    action: str
    entity_type: str
    entity_id: str
    metadata_json: dict | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
