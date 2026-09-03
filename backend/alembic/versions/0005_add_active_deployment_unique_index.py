"""enforce at most one active deployment per app

Revision ID: 0005_active_deployment_index
Revises: 0004_add_server_known_host_key
Create Date: 2026-08-31

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_active_deployment_index"
down_revision: str | None = "0004_add_server_known_host_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTIVE_STATUSES = "('pending', 'running')"


def upgrade() -> None:
    # Reclaim any rows left non-terminal by an interrupted process, otherwise the
    # unique index below cannot be created on an existing database.
    op.execute(
        sa.text(
            "UPDATE deployments SET status = 'failed', "
            "error_message = COALESCE(error_message, 'Deployment was interrupted and "
            "has been marked failed during migration.') "
            f"WHERE status IN {ACTIVE_STATUSES} AND id NOT IN ("
            "  SELECT id FROM ("
            "    SELECT DISTINCT ON (app_id) id FROM deployments "
            f"    WHERE status IN {ACTIVE_STATUSES} ORDER BY app_id, created_at DESC"
            "  ) AS keep"
            ")"
        )
        if op.get_bind().dialect.name == "postgresql"
        else sa.text(
            "UPDATE deployments SET status = 'failed' "
            f"WHERE status IN {ACTIVE_STATUSES} AND id NOT IN ("
            "  SELECT MAX(id) FROM deployments "
            f"  WHERE status IN {ACTIVE_STATUSES} GROUP BY app_id"
            ")"
        )
    )
    op.create_index(
        "uq_deployments_active_per_app",
        "deployments",
        ["app_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN {ACTIVE_STATUSES}"),
        sqlite_where=sa.text(f"status IN {ACTIVE_STATUSES}"),
    )


def downgrade() -> None:
    op.drop_index("uq_deployments_active_per_app", table_name="deployments")
