"""add the superseded deployment status (v3 spec §4.3)

Revision ID: 0014_superseded_deployment_status
Revises: 0013_email_verification
Create Date: 2026-11-01

A newer deployment replacing an app's queued one must mark the old row
`superseded` (stale code must not run) instead of refusing with 409.

The deployment status column is a non-native enum rendered as VARCHAR on both
PostgreSQL and SQLite. PostgreSQL carries no CHECK over the values (see 0007),
so this migration is a no-op there. SQLite's CHECK constraint lists the
allowed values, so the table is rebuilt in batch mode from an explicit
definition that includes `superseded` — the same approach as 0007, updated for
the columns and index predicate added since (0008 healthcheck columns, 0009
commit_message, 0012 widened partial-index predicate).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_superseded_deployment_status"
down_revision: str | None = "0013_email_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_STATUS_VALUES = (
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
NEW_STATUS_VALUES = (*OLD_STATUS_VALUES, "superseded")

DISPATCHABLE_STATUS_PREDICATE = (
    "status IN ('pending', 'cloning', 'building', 'testing', 'deploying', 'health_check', 'running')"
)


def _bind() -> sa.engine.Connection:
    return op.get_bind()


def _is_postgresql() -> bool:
    return _bind().dialect.name == "postgresql"


def _deployments_table(status_values: Sequence[str]) -> sa.Table:
    """The deployments table as it exists after 0012, with a CHECK over the
    given status values (mirrors 0007's explicit copy_from definition)."""
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
        sa.Column("commit_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("triggered_by", sa.String(length=120)),
        sa.Column("exit_code", sa.Integer()),
        sa.Column("error_message", sa.Text()),
        sa.Column("healthcheck_url", sa.String(length=500)),
        sa.Column("healthcheck_status_code", sa.Integer()),
        sa.Column("healthcheck_ok", sa.Boolean()),
        sa.Column("healthcheck_error", sa.Text()),
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
            sqlite_where=sa.text(DISPATCHABLE_STATUS_PREDICATE),
        ),
    )
    table.append_constraint(
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{value}'" for value in status_values) + ")",
            name="ck_deployments_status_valid",
        )
    )
    return table


def upgrade() -> None:
    if _is_postgresql():
        # VARCHAR column, no CHECK constraint: nothing to change.
        return

    with op.batch_alter_table(
        "deployments",
        copy_from=_deployments_table(OLD_STATUS_VALUES),
        recreate="always",
    ) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(*OLD_STATUS_VALUES, name="deploymentstatus", native_enum=False),
            type_=sa.Enum(*NEW_STATUS_VALUES, name="deploymentstatus", native_enum=False),
            existing_nullable=False,
        )
        batch_op.drop_constraint("ck_deployments_status_valid", type_="check")
        batch_op.create_check_constraint(
            "ck_deployments_status_valid",
            "status IN (" + ", ".join(f"'{value}'" for value in NEW_STATUS_VALUES) + ")",
        )


def downgrade() -> None:
    stuck = _bind().execute(
        sa.text("SELECT count(*) FROM deployments WHERE status = 'superseded'")
    ).scalar_one()
    if stuck:
        raise RuntimeError(
            f"{stuck} deployment row(s) use the superseded status; "
            "resolve them before downgrading."
        )
    if _is_postgresql():
        return

    with op.batch_alter_table(
        "deployments",
        copy_from=_deployments_table(NEW_STATUS_VALUES),
        recreate="always",
    ) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(*NEW_STATUS_VALUES, name="deploymentstatus", native_enum=False),
            type_=sa.Enum(*OLD_STATUS_VALUES, name="deploymentstatus", native_enum=False),
            existing_nullable=False,
        )
        batch_op.drop_constraint("ck_deployments_status_valid", type_="check")
        batch_op.create_check_constraint(
            "ck_deployments_status_valid",
            "status IN (" + ", ".join(f"'{value}'" for value in OLD_STATUS_VALUES) + ")",
        )
