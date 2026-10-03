import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import UUIDPrimaryKeyMixin


class WebhookDeliveryResult(str, enum.Enum):
    deployed = "deployed"
    queued = "queued"
    ignored = "ignored"
    rejected = "rejected"
    error = "error"


class WebhookDelivery(UUIDPrimaryKeyMixin, Base):
    """One received GitHub webhook, deduplicated by delivery id (spec §40).

    Replay protection: GitHub sends a unique X-GitHub-Delivery per dispatch;
    a repeated delivery id is answered without side effects.
    """

    __tablename__ = "webhook_deliveries"
    __table_args__ = (Index("ix_webhook_deliveries_app_id", "app_id"),)

    # Deliberately not a FK: deliveries for since-deleted apps stay auditable.
    app_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    delivery_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[WebhookDeliveryResult] = mapped_column(String(64), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
