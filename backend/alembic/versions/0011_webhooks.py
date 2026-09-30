"""github webhook automation: app webhook secret + delivery log

Revision ID: 0011_webhooks
Revises: 0010_environments
Create Date: 2026-09-10

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_webhooks"
down_revision: str | None = "0010_environments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("apps", sa.Column("encrypted_webhook_secret", sa.Text(), nullable=True))
    op.add_column("apps", sa.Column("auto_deploy", sa.Boolean(), nullable=False, server_default="true"))
    # Container resource limits applied by the agent (spec §50).
    op.add_column("apps", sa.Column("cpu_limit", sa.String(length=32), nullable=True))
    op.add_column("apps", sa.Column("memory_limit", sa.String(length=32), nullable=True))
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        # Not a FK: GitHub retries deliveries for deleted apps, and the log is
        # the audit trail of what happened.
        sa.Column("app_id", sa.Uuid(), nullable=True),
        sa.Column("delivery_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=True),
        sa.Column("result", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_webhook_deliveries_delivery_id", "webhook_deliveries", ["delivery_id"])


def downgrade() -> None:
    op.drop_column("apps", "memory_limit")
    op.drop_column("apps", "cpu_limit")
    op.drop_index("ix_webhook_deliveries_delivery_id", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_column("apps", "auto_deploy")
    op.drop_column("apps", "encrypted_webhook_secret")
