import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class App(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "apps"
    __table_args__ = (Index("ix_apps_owner_id", "owner_id"),)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    server_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("servers.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    repository_url: Mapped[str] = mapped_column(String(500), nullable=False)
    branch: Mapped[str] = mapped_column(String(120), default="main", server_default="main", nullable=False)
    app_path: Mapped[str] = mapped_column(String(500), nullable=False)
    service_name: Mapped[str | None] = mapped_column(String(120))
    deploy_command: Mapped[str] = mapped_column(Text, nullable=False)
    restart_command: Mapped[str | None] = mapped_column(Text)
    healthcheck_url: Mapped[str | None] = mapped_column(String(500))
    current_commit: Mapped[str | None] = mapped_column(String(64))
    last_successful_commit: Mapped[str | None] = mapped_column(String(64))

    owner = relationship("User", back_populates="apps")
    server = relationship("Server", back_populates="apps")
    deployments = relationship("Deployment", back_populates="app", cascade="all, delete-orphan")
