"""create agents and agent_registration_tokens

Revision ID: 0006_create_agents
Revises: 0005_active_deployment_index
Create Date: 2026-09-03

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_create_agents"
down_revision: str | None = "0005_active_deployment_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "server_id",
            sa.Uuid(),
            sa.ForeignKey("servers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("reported_status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("agent_version", sa.String(length=64), nullable=True),
        sa.Column("os_name", sa.String(length=64), nullable=True),
        sa.Column("arch", sa.String(length=32), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agents_owner_id", "agents", ["owner_id"])
    op.create_index("ix_agents_server_id", "agents", ["server_id"])

    op.create_table(
        "agent_registration_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "server_id",
            sa.Uuid(),
            sa.ForeignKey("servers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_registration_tokens_owner_id", "agent_registration_tokens", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_registration_tokens_owner_id", table_name="agent_registration_tokens")
    op.drop_table("agent_registration_tokens")
    op.drop_index("ix_agents_server_id", table_name="agents")
    op.drop_index("ix_agents_owner_id", table_name="agents")
    op.drop_table("agents")
