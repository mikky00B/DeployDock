import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import UUIDPrimaryKeyMixin


class EmailVerificationCode(UUIDPrimaryKeyMixin, Base):
    """One emailed verification code, stored hashed (signup purpose for now).

    Only the newest unconsumed code for a user is verifiable; every wrong
    attempt increments `attempts`, and after the limit the code is burned and
    a fresh one must be requested.
    """

    __tablename__ = "email_verification_codes"
    __table_args__ = (
        Index("ix_email_verification_codes_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, server_default="signup")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Client-side default (microsecond precision): codes issued within the same
    # second — register plus an immediate gated login — must sort
    # deterministically when the newest one is selected.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User")
