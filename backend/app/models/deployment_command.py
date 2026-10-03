import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

ACTIVE_COMMAND_STATUSES_SQL = "status IN ('queued', 'claimed')"


class AgentCommandKind(str, enum.Enum):
    deploy = "deploy"
    rollback = "rollback"


class AgentCommandStatus(str, enum.Enum):
    queued = "queued"
    claimed = "claimed"
    completed = "completed"
    failed = "failed"


class DeploymentCommand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A unit of work handed to a DeployDock agent (spec §25).

    The payload is self-contained: the agent never queries the control plane
    for context, so a claimed command can execute even if this API is briefly
    unavailable (spec §77 success criterion 17).

    `claim_token` is minted at claim time; the agent echoes it on result
    submission so a stale poller cannot close out a command it does not own.
    """

    __tablename__ = "deployment_commands"
    __table_args__ = (
        Index("ix_deployment_commands_agent_status", "agent_id", "status"),
        Index("ix_deployment_commands_deployment_id", "deployment_id"),
        # At most one live command per deployment: two dispatch calls racing
        # (webhook + promotion) must not hand the agent the same deploy twice.
        # Mirrors the one-active-deployment guard on `deployments`.
        Index(
            "uq_deployment_commands_active_per_deployment",
            "deployment_id",
            unique=True,
            postgresql_where=text(ACTIVE_COMMAND_STATUSES_SQL),
            sqlite_where=text(ACTIVE_COMMAND_STATUSES_SQL),
        ),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("deployments.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[AgentCommandKind] = mapped_column(
        Enum(AgentCommandKind, native_enum=False),
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[AgentCommandStatus] = mapped_column(
        Enum(AgentCommandStatus, native_enum=False),
        default=AgentCommandStatus.queued,
        server_default=AgentCommandStatus.queued.value,
        nullable=False,
    )
    claim_token: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    deployment = relationship("Deployment")
    agent = relationship("Agent")
