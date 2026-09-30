"""agent command queue, app port, deployment commit message

Revision ID: 0009_deployment_commands
Revises: 0008_deployment_healthcheck_result
Create Date: 2026-09-10

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_deployment_commands"
down_revision: str | None = "0008_deployment_healthcheck_result"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deployment_commands",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "agent_id",
            sa.Uuid(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "deployment_id",
            sa.Uuid(),
            sa.ForeignKey("deployments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("claim_token", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_deployment_commands_agent_status",
        "deployment_commands",
        ["agent_id", "status"],
    )
    op.create_index(
        "ix_deployment_commands_deployment_id",
        "deployment_commands",
        ["deployment_id"],
    )

    op.add_column("apps", sa.Column("port", sa.Integer(), nullable=True))
    op.add_column("deployments", sa.Column("commit_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("deployments", "commit_message")
    op.drop_column("apps", "port")
    op.drop_index("ix_deployment_commands_deployment_id", table_name="deployment_commands")
    op.drop_index("ix_deployment_commands_agent_status", table_name="deployment_commands")
    op.drop_table("deployment_commands")
