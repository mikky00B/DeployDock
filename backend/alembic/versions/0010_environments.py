"""environments, environment variables, domains

Revision ID: 0010_environments
Revises: 0009_deployment_commands
Create Date: 2026-09-10

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_environments"
down_revision: str | None = "0009_deployment_commands"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "environments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("app_id", sa.Uuid(), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", sa.Uuid(), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("auto_deploy", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("health_path", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("app_id", "name", name="uq_environments_app_name"),
    )
    op.create_index("ix_environments_app_id", "environments", ["app_id"])

    op.create_table(
        "environment_variables",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "environment_id",
            sa.Uuid(),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("environment_id", "key", name="uq_environment_variables_key"),
    )
    op.create_index(
        "ix_environment_variables_environment_id",
        "environment_variables",
        ["environment_id"],
    )

    op.create_table(
        "domains",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "environment_id",
            sa.Uuid(),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("ssl_status", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("last_verification_error", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_domains_environment_id", "domains", ["environment_id"])


def downgrade() -> None:
    op.drop_index("ix_domains_environment_id", table_name="domains")
    op.drop_table("domains")
    op.drop_index("ix_environment_variables_environment_id", table_name="environment_variables")
    op.drop_table("environment_variables")
    op.drop_index("ix_environments_app_id", table_name="environments")
    op.drop_table("environments")
