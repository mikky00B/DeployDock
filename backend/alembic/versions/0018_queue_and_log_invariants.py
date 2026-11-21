"""queue and log invariants (audit M10, M7)

Revision ID: 0018_queue_and_log_invariants
Revises: 0017_deployment_image_ref
Create Date: 2026-11-21

1. At most one queued deployment per app: two concurrent webhook pushes could
   both insert queued rows (the dispatchable index deliberately excludes
   queued). The newest supersedes the oldest — stale code must not run — so
   duplicates are resolved to the newest per app before the index.
2. Unique (deployment_id, sequence) on deployment_logs: sequences are
   allocated from max() at ingestion time; without the constraint, two
   concurrent posts could interleave duplicates and the SSE stream would
   silently drop one of them on the client. Duplicate rows (same
   deployment+sequence) are removed, keeping the earliest.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_queue_and_log_invariants"
down_revision: str | None = "0017_deployment_image_ref"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _bind() -> sa.engine.Connection:
    return op.get_bind()


def _is_postgresql() -> bool:
    return _bind().dialect.name == "postgresql"


def upgrade() -> None:
    # Resolve queued duplicates: keep the newest per app (it is the deployment
    # the user intended), supersede the rest.
    if _is_postgresql():
        op.execute(
            sa.text(
                "UPDATE deployments SET status = 'superseded', finished_at = now() "
                "WHERE status = 'queued' AND id NOT IN ("
                "  SELECT id FROM ("
                "    SELECT DISTINCT ON (app_id) id FROM deployments "
                "    WHERE status = 'queued' ORDER BY app_id, created_at DESC"
                "  ) AS keep"
                ")"
            )
        )
    else:
        op.execute(
            sa.text(
                "UPDATE deployments SET status = 'superseded', finished_at = CURRENT_TIMESTAMP "
                "WHERE status = 'queued' AND id NOT IN ("
                "  SELECT id FROM (SELECT MAX(id) FROM deployments WHERE status = 'queued' GROUP BY app_id)"
                ")"
            )
        )

    op.create_index(
        "uq_deployments_queued_per_app",
        "deployments",
        ["app_id"],
        unique=True,
        postgresql_where=sa.text("status = 'queued'"),
        sqlite_where=sa.text("status = 'queued'"),
    )

    # Resolve duplicate log sequences: keep the earliest row per
    # (deployment_id, sequence) — it is what the stream showed first.
    if _is_postgresql():
        op.execute(
            sa.text(
                "DELETE FROM deployment_logs a USING deployment_logs b "
                "WHERE a.deployment_id = b.deployment_id AND a.sequence = b.sequence "
                "AND a.id > b.id"
            )
        )
    else:
        op.execute(
            sa.text(
                "DELETE FROM deployment_logs WHERE id IN ("
                "  SELECT a.id FROM deployment_logs a, deployment_logs b "
                "  WHERE a.deployment_id = b.deployment_id AND a.sequence = b.sequence "
                "  AND a.id > b.id)"
            )
        )

    op.create_index(
        "uq_deployment_logs_sequence",
        "deployment_logs",
        ["deployment_id", "sequence"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_deployment_logs_sequence", table_name="deployment_logs")
    op.drop_index("uq_deployments_queued_per_app", table_name="deployments")
