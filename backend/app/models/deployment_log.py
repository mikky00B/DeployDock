import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class DeploymentLogStream(str, enum.Enum):
    stdout = "stdout"
    stderr = "stderr"
    system = "system"


class DeploymentLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deployment_logs"
    __table_args__ = (
        # The stream ordering and resume cursor depend on sequences being
        # unique per deployment (audit M7); the ingestion allocator settles
        # duplicates against this constraint, not just in memory.
        Index(
            "uq_deployment_logs_sequence",
            "deployment_id",
            "sequence",
            unique=True,
        ),
    )

    deployment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("deployments.id", ondelete="CASCADE"),
        nullable=False,
    )
    stream: Mapped[DeploymentLogStream] = mapped_column(
        Enum(DeploymentLogStream, native_enum=False),
        nullable=False,
    )
    line: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    deployment = relationship("Deployment", back_populates="logs")
