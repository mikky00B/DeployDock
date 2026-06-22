import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class DeploymentStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    canceled = "canceled"


class DeploymentKind(str, enum.Enum):
    deploy = "deploy"
    rollback = "rollback"


class Deployment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deployments"
    __table_args__ = (
        Index("ix_deployments_app_id", "app_id"),
        Index("ix_deployments_status", "status"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("apps.id", ondelete="CASCADE"),
        nullable=False,
    )
    server_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("servers.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(DeploymentStatus, native_enum=False),
        default=DeploymentStatus.pending,
        server_default=DeploymentStatus.pending.value,
        nullable=False,
    )
    kind: Mapped[DeploymentKind] = mapped_column(
        Enum(DeploymentKind, native_enum=False),
        default=DeploymentKind.deploy,
        server_default=DeploymentKind.deploy.value,
        nullable=False,
    )
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    previous_commit_sha: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    triggered_by: Mapped[str | None] = mapped_column(String(120))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)

    owner = relationship("User", back_populates="deployments")
    app = relationship("App", back_populates="deployments")
    server = relationship("Server", back_populates="deployments")
    logs = relationship(
        "DeploymentLog",
        back_populates="deployment",
        cascade="all, delete-orphan",
        order_by="DeploymentLog.sequence",
    )
