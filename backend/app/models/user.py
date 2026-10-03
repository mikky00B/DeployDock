from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    # Whether the address was confirmed with an emailed code. Existing rows
    # migrated as verified: only accounts created after the feature must prove
    # their address.
    email_verified: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    servers = relationship("Server", back_populates="owner", cascade="all, delete-orphan")
    apps = relationship("App", back_populates="owner", cascade="all, delete-orphan")
    deployments = relationship("Deployment", back_populates="owner", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="owner", cascade="all, delete-orphan")
