"""add pinned ssh host key columns to servers

Revision ID: 0004_add_server_known_host_key
Revises: 0003_add_server_public_ssh_key
Create Date: 2026-08-31

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_add_server_known_host_key"
down_revision: str | None = "0003_add_server_public_ssh_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("servers", sa.Column("known_host_key", sa.Text(), nullable=True))
    op.add_column("servers", sa.Column("known_host_key_fingerprint", sa.String(length=255), nullable=True))
    op.add_column(
        "servers",
        sa.Column("known_host_key_pinned_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("servers", "known_host_key_pinned_at")
    op.drop_column("servers", "known_host_key_fingerprint")
    op.drop_column("servers", "known_host_key")
