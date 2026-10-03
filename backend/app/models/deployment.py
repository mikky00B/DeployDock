import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class DeploymentStatus(str, enum.Enum):
    """Lifecycle of a deployment (spec §13).

    The pipeline states between ``pending`` and ``success``/``failed`` become
    active as the agent-driven engine (Phase 3) reports stage events; the SSH
    bridge runner only uses ``pending``/``running`` for now.
    """

    pending = "pending"
    queued = "queued"
    cloning = "cloning"
    building = "building"
    testing = "testing"
    deploying = "deploying"
    health_check = "health_check"
    running = "running"
    success = "success"
    failed = "failed"
    canceled = "canceled"
    rolled_back = "rolled_back"


# Canonical status groups. Kept next to the enum so the concurrency guard,
# the SSE stream, and the orphan sweep cannot drift apart.
ACTIVE_DEPLOYMENT_STATUSES = (
    DeploymentStatus.pending,
    DeploymentStatus.queued,
    DeploymentStatus.cloning,
    DeploymentStatus.building,
    DeploymentStatus.testing,
    DeploymentStatus.deploying,
    DeploymentStatus.health_check,
    DeploymentStatus.running,
)

TERMINAL_DEPLOYMENT_STATUSES = (
    DeploymentStatus.success,
    DeploymentStatus.failed,
    DeploymentStatus.canceled,
    DeploymentStatus.rolled_back,
)

# Active statuses that occupy the one-deployment-per-app slot proper. `queued`
# is active (it blocks nothing else from queueing) but exempt from the guard:
# queued rows exist precisely to wait for one of these to finish (spec §42).
DISPATCHABLE_DEPLOYMENT_STATUSES = tuple(
    status for status in ACTIVE_DEPLOYMENT_STATUSES if status is not DeploymentStatus.queued
)

# The partial index predicate, derived from the tuple so the model, the
# service-layer guard, and the migration can never drift apart. Before this was
# derived, the index only covered ('pending', 'running') — so once an agent
# moved a deployment into a pipeline stage, the database stopped enforcing the
# guard and only the (racy) service-layer check remained.
DISPATCHABLE_STATUS_PREDICATE = "status IN ({})".format(
    ", ".join(f"'{status.value}'" for status in DISPATCHABLE_DEPLOYMENT_STATUSES)
)


class DeploymentKind(str, enum.Enum):
    deploy = "deploy"
    rollback = "rollback"


class Deployment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deployments"
    __table_args__ = (
        Index("ix_deployments_app_id", "app_id"),
        Index("ix_deployments_status", "status"),
        # At most one dispatchable deployment per app (every active status
        # except `queued`, which exists to wait behind these). This is the
        # authoritative concurrency guard: the service-layer check is a
        # friendlier error path, but only the database can settle a race
        # between two API workers.
        Index(
            "uq_deployments_active_per_app",
            "app_id",
            unique=True,
            postgresql_where=text(DISPATCHABLE_STATUS_PREDICATE),
            sqlite_where=text(DISPATCHABLE_STATUS_PREDICATE),
        ),
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
    # Head commit message when the deploy was triggered by a webhook (spec §73).
    commit_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    triggered_by: Mapped[str | None] = mapped_column(String(120))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    # Health-check result reported by the agent engine (spec §18). A deployment
    # only becomes success after its health check passed.
    healthcheck_url: Mapped[str | None] = mapped_column(String(500))
    healthcheck_status_code: Mapped[int | None] = mapped_column(Integer)
    healthcheck_ok: Mapped[bool | None] = mapped_column(Boolean)
    healthcheck_error: Mapped[str | None] = mapped_column(Text)

    owner = relationship("User", back_populates="deployments")
    app = relationship("App", back_populates="deployments")
    server = relationship("Server", back_populates="deployments")
    logs = relationship(
        "DeploymentLog",
        back_populates="deployment",
        cascade="all, delete-orphan",
        order_by="DeploymentLog.sequence",
    )
