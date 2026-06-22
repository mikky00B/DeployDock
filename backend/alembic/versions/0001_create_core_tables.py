"""create core tables

Revision ID: 0001_create_core_tables
Revises:
Create Date: 2026-06-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_create_core_tables"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "servers",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), server_default="22", nullable=False),
        sa.Column(
            "auth_type",
            sa.Enum("ssh_key", name="serverauthtype", native_enum=False),
            server_default="ssh_key",
            nullable=False,
        ),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("encrypted_private_key", sa.Text(), nullable=False),
        sa.Column("private_key_fingerprint", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("unknown", "connected", "unreachable", name="serverstatus", native_enum=False),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("last_connection_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_connection_error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_servers_owner_id", "servers", ["owner_id"], unique=False)

    op.create_table(
        "apps",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("server_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("repository_url", sa.String(length=500), nullable=False),
        sa.Column("branch", sa.String(length=120), server_default="main", nullable=False),
        sa.Column("app_path", sa.String(length=500), nullable=False),
        sa.Column("service_name", sa.String(length=120), nullable=True),
        sa.Column("deploy_command", sa.Text(), nullable=False),
        sa.Column("restart_command", sa.Text(), nullable=True),
        sa.Column("healthcheck_url", sa.String(length=500), nullable=True),
        sa.Column("current_commit", sa.String(length=64), nullable=True),
        sa.Column("last_successful_commit", sa.String(length=64), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["server_id"], ["servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_apps_owner_id", "apps", ["owner_id"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=120), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_owner_id", "audit_logs", ["owner_id"], unique=False)

    op.create_table(
        "deployments",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("app_id", sa.Uuid(), nullable=False),
        sa.Column("server_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "success",
                "failed",
                "canceled",
                name="deploymentstatus",
                native_enum=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("previous_commit_sha", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("triggered_by", sa.String(length=120), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["server_id"], ["servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deployments_app_id", "deployments", ["app_id"], unique=False)
    op.create_index("ix_deployments_status", "deployments", ["status"], unique=False)

    op.create_table(
        "deployment_logs",
        sa.Column("deployment_id", sa.Uuid(), nullable=False),
        sa.Column(
            "stream",
            sa.Enum("stdout", "stderr", "system", name="deploymentlogstream", native_enum=False),
            nullable=False,
        ),
        sa.Column("line", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_deployment_logs_deployment_id_sequence",
        "deployment_logs",
        ["deployment_id", "sequence"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_deployment_logs_deployment_id_sequence", table_name="deployment_logs")
    op.drop_table("deployment_logs")

    op.drop_index("ix_deployments_status", table_name="deployments")
    op.drop_index("ix_deployments_app_id", table_name="deployments")
    op.drop_table("deployments")

    op.drop_index("ix_audit_logs_owner_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_apps_owner_id", table_name="apps")
    op.drop_table("apps")

    op.drop_index("ix_servers_owner_id", table_name="servers")
    op.drop_table("servers")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
