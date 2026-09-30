import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class DomainStatus(str, enum.Enum):
    pending = "pending"
    verified = "verified"
    failed = "failed"


class SSLStatus(str, enum.Enum):
    none = "none"
    pending = "pending"
    active = "active"
    error = "error"


class Environment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A deployable target of an app: server + health config + variables (spec §12)."""

    __tablename__ = "environments"
    __table_args__ = (
        UniqueConstraint("app_id", "name", name="uq_environments_app_name"),
        Index("ix_environments_app_id", "app_id"),
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
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    auto_deploy: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    health_path: Mapped[str | None] = mapped_column(String(500))

    app = relationship("App")
    variables = relationship(
        "EnvironmentVariable",
        back_populates="environment",
        cascade="all, delete-orphan",
    )
    domains = relationship(
        "Domain",
        back_populates="environment",
        cascade="all, delete-orphan",
    )


class EnvironmentVariable(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One variable of an environment (spec §38).

    `encrypted_value` is encrypted with the control-plane encryption key; the
    plaintext is never returned by the API (masked reads only).
    """

    __tablename__ = "environment_variables"
    __table_args__ = (
        UniqueConstraint("environment_id", "key", name="uq_environment_variables_key"),
        Index("ix_environment_variables_environment_id", "environment_id"),
    )

    environment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)

    environment = relationship("Environment", back_populates="variables")


class Domain(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A domain attached to an environment (spec §36)."""

    __tablename__ = "domains"
    __table_args__ = (Index("ix_domains_environment_id", "environment_id"),)

    environment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
    )
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[DomainStatus] = mapped_column(
        Enum(DomainStatus, native_enum=False),
        default=DomainStatus.pending,
        server_default=DomainStatus.pending.value,
        nullable=False,
    )
    ssl_status: Mapped[SSLStatus] = mapped_column(
        Enum(SSLStatus, native_enum=False),
        default=SSLStatus.none,
        server_default=SSLStatus.none.value,
        nullable=False,
    )
    last_verification_error: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    environment = relationship("Environment", back_populates="domains")
