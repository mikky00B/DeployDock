"""track deployment progress for orphan sweeping (audit H6)

Revision ID: 0016_deployment_last_progress_at
Revises: 0015_agent_tenant_isolation
Create Date: 2026-11-21

The orphan sweep used `created_at`, so a legitimate long build could be
marked failed by the periodic sweep (or by another uvicorn worker) while it
was still running. `last_progress_at` is advanced on every log line, agent
event, and runner checkpoint; the sweep now ages deployments out from their
last observable activity.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_deployment_last_progress_at"
down_revision: str | None = "0015_agent_tenant_isolation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "deployments",
        sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill from created_at: existing rows have made no observable progress
    # since creation, which is exactly what the column means. Recently created
    # rows therefore survive the first sweep; genuinely stuck ones age out.
    op.execute("UPDATE deployments SET last_progress_at = created_at")


def downgrade() -> None:
    op.drop_column("deployments", "last_progress_at")
