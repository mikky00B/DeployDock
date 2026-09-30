"""extend deployment status values

Revision ID: 0007_deployment_status_pipeline
Revises: 0006_create_agents
Create Date: 2026-09-04

The deployment status column is a non-native enum rendered as VARCHAR on both
PostgreSQL and SQLite. The new spec §13 pipeline values are longer than the
previous ones ("health_check" is 12 characters, the longest old value is 8),
so PostgreSQL needs an explicit widening.

SQLite cannot ALTER a column type, so the table is rebuilt in batch mode from
an explicit definition that carries a CHECK constraint over the full §13 status
list (the original table was created without one). The rebuild preserves every
index, including the partial unique index that enforces at most one active
deployment per app.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_deployment_status_pipeline"
down_revision: str | None = "0006_create_agents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_STATUS_VALUES = ("pending", "running", "success", "failed", "canceled")
NEW_STATUS_VALUES = (
    "pending",
    "queued",
    "cloning",
    "building",
    "testing",
    "deploying",
    "health_check",
    "running",
    "success",
    "failed",
    "canceled",
    "rolled_back",
)


def _bind() -> sa.engine.Connection:
    return op.get_bind()


def _is_postgresql() -> bool:
    return _bind().dialect.name == "postgresql"


def _deployments_table(status_values: Sequence[str], *, with_status_check: bool) -> sa.Table:
    """The deployments table as it exists for the given status values.

    Mirrors 0001/0002 so the batch rebuilds start from an accurate copy_from
    (SQLAlchemy 2.0 renders non-native enums as plain VARCHAR without a CHECK,
    which is why the constraint is added/dropped explicitly in the ops below).
    """
    metadata = sa.MetaData()
    table = sa.Table(
        "deployments",
        metadata,
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("app_id", sa.Uuid(), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", sa.Uuid(), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*status_values, name="deploymentstatus", native_enum=False),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("commit_sha", sa.String(length=64)),
        sa.Column("previous_commit_sha", sa.String(length=64)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("triggered_by", sa.String(length=120)),
        sa.Column("exit_code", sa.Integer()),
        sa.Column("error_message", sa.Text()),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("deploy", "rollback", name="deploymentkind", native_enum=False),
            server_default="deploy",
            nullable=False,
        ),
        sa.Index("ix_deployments_app_id", "app_id"),
        sa.Index("ix_deployments_status", "status"),
        sa.Index(
            "uq_deployments_active_per_app",
            "app_id",
            unique=True,
            sqlite_where=sa.text("status IN ('pending', 'running')"),
        ),
    )
    if with_status_check:
        table.append_constraint(
            sa.CheckConstraint(
                "status IN (" + ", ".join(f"'{value}'" for value in status_values) + ")",
                name="ck_deployments_status_valid",
            )
        )
    return table


def _count_pipeline_rows() -> int:
    return _bind().execute(
        sa.text(
            "SELECT count(*) FROM deployments "
            "WHERE status NOT IN ('pending', 'running', 'success', 'failed', 'canceled')"
        )
    ).scalar_one()


def upgrade() -> None:
    if _is_postgresql():
        # Old rows can only be in the original values, so no data rewrite is
        # needed - the column just gets wider.
        op.alter_column(
            "deployments",
            "status",
            type_=sa.Enum(*NEW_STATUS_VALUES, name="deploymentstatus", native_enum=False),
            existing_type=sa.Enum(*OLD_STATUS_VALUES, name="deploymentstatus", native_enum=False),
            existing_nullable=False,
            postgresql_using="status::varchar",
        )
        return

    # SQLite: rebuild the table so the DDL carries the full status CHECK.
    with op.batch_alter_table(
        "deployments",
        copy_from=_deployments_table(OLD_STATUS_VALUES, with_status_check=False),
        recreate="always",
    ) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(*OLD_STATUS_VALUES, name="deploymentstatus", native_enum=False),
            type_=sa.Enum(*NEW_STATUS_VALUES, name="deploymentstatus", native_enum=False),
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_deployments_status_valid",
            "status IN (" + ", ".join(f"'{value}'" for value in NEW_STATUS_VALUES) + ")",
        )


def downgrade() -> None:
    # Refuse to destroy non-terminal pipeline rows implicitly; if any exist the
    # operator must resolve them first (fail closed rather than truncate).
    stuck = _count_pipeline_rows()
    if stuck:
        raise RuntimeError(
            f"{stuck} deployment row(s) still use pipeline statuses; "
            "cancel or resolve them before downgrading."
        )
    if _is_postgresql():
        op.alter_column(
            "deployments",
            "status",
            type_=sa.Enum(*OLD_STATUS_VALUES, name="deploymentstatus", native_enum=False),
            existing_type=sa.Enum(*NEW_STATUS_VALUES, name="deploymentstatus", native_enum=False),
            existing_nullable=False,
            postgresql_using="status::varchar",
        )
        return

    with op.batch_alter_table(
        "deployments",
        copy_from=_deployments_table(NEW_STATUS_VALUES, with_status_check=True),
        recreate="always",
    ) as batch_op:
        batch_op.drop_constraint("ck_deployments_status_valid", type_="check")
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(*NEW_STATUS_VALUES, name="deploymentstatus", native_enum=False),
            type_=sa.Enum(*OLD_STATUS_VALUES, name="deploymentstatus", native_enum=False),
            existing_nullable=False,
        )
