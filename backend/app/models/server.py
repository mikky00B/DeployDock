import enum
import uuid

from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class ServerAuthType(str, enum.Enum):
    ssh_key = "ssh_key"


class ServerStatus(str, enum.Enum):
    unknown = "unknown"
    connected = "connected"
    unreachable = "unreachable"


class Server(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "servers"
    __table_args__ = (Index("ix_servers_owner_id", "owner_id"),)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=22, server_default="22", nullable=False)
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    auth_type: Mapped[ServerAuthType] = mapped_column(
        Enum(ServerAuthType, native_enum=False),
        default=ServerAuthType.ssh_key,
        server_default=ServerAuthType.ssh_key.value,
        nullable=False,
    )
    encrypted_private_key: Mapped[str] = mapped_column(Text, nullable=False)
    public_ssh_key: Mapped[str | None] = mapped_column(Text)
    private_key_fingerprint: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[ServerStatus] = mapped_column(
        Enum(ServerStatus, native_enum=False),
        default=ServerStatus.unknown,
        server_default=ServerStatus.unknown.value,
        nullable=False,
    )
    last_connection_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_connection_error: Mapped[str | None] = mapped_column(Text)

    owner = relationship("User", back_populates="servers")
    apps = relationship("App", back_populates="server", cascade="all, delete-orphan")
    deployments = relationship("Deployment", back_populates="server")
