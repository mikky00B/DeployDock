import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class AgentReportedStatus(str, enum.Enum):
    """What the agent last claimed about itself, distinct from derived liveness.

    Liveness (`online`/`offline`) is derived from `last_heartbeat_at` and is
    never stored, so agent/server clock drift cannot flip persisted state.
    """

    active = "active"
    retired = "retired"


class Agent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A DeployDock agent installed on a managed VPS.

    `token_hash` is the SHA-256 hex digest of the agent's bearer token; the
    plaintext token is shown exactly once at registration (and on rotation).
    """

    __tablename__ = "agents"
    __table_args__ = (
        Index("ix_agents_owner_id", "owner_id"),
        Index("ix_agents_server_id", "server_id"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    server_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("servers.id", ondelete="SET NULL"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    reported_status: Mapped[AgentReportedStatus] = mapped_column(
        Enum(AgentReportedStatus, native_enum=False),
        default=AgentReportedStatus.active,
        server_default=AgentReportedStatus.active.value,
        nullable=False,
    )
    agent_version: Mapped[str | None] = mapped_column(String(64))
    os_name: Mapped[str | None] = mapped_column(String(64))
    arch: Mapped[str | None] = mapped_column(String(32))
    metrics: Mapped[dict | None] = mapped_column(JSON)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner = relationship("User")
    server = relationship("Server")


class AgentRegistrationToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A short-lived, single-use token that lets an agent call register once.

    Stored as a SHA-256 hash like agent tokens; the plaintext is returned by the
    minting call and never persisted.
    """

    __tablename__ = "agent_registration_tokens"
    __table_args__ = (Index("ix_agent_registration_tokens_owner_id", "owner_id"),)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    server_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("servers.id", ondelete="SET NULL"),
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner = relationship("User")
