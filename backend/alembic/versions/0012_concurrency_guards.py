"""widen deployment concurrency guard, add command uniqueness

Revision ID: 0012_concurrency_guards
Revises: 0011_webhooks
Create Date: 2026-10-01

Two database-level concurrency fixes:

1. The partial unique index on deployments.app_id only covered
   ('pending', 'running'). Once the agent pipeline moved a deployment into
   cloning/building/deploying, the database stopped enforcing
   one-active-deployment-per-app, leaving only the racy service-layer check.
   The predicate is widened to every dispatchable status (all active statuses
   except 'queued', which must be allowed to wait behind an active one).

2. deployment_commands had no uniqueness guard, so two dispatch calls racing
   (webhook path vs promotion path) could hand the agent the same deployment
   twice. A partial unique index on deployment_id for queued/claimed commands
   makes the database the arbiter, matching the deployments guard.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_concurrency_guards"
down_revision: str | None = "0011_webhooks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_ACTIVE_STATUSES = "('pending', 'running')"
DISPATCHABLE_STATUSES = (
    "'pending', 'cloning', 'building', 'testing', 'deploying', 'health_check', 'running'"
)
ACTIVE_COMMAND_STATUSES = "('queued', 'claimed')"


def _bind() -> sa.engine.Connection:
    return op.get_bind()


def _is_postgresql() -> bool:
    return _bind().dialect.name == "postgresql"


def upgrade() -> None:
    # Reclaim any rows that already violate the widened predicate (two
    # pipeline-stage deployments for one app) before the index can be created.
    # Keep the newest per app; mark the rest failed.
    if _is_postgresql():
        op.execute(
            sa.text(
                "UPDATE deployments SET status = 'failed', "
                "error_message = COALESCE(error_message, 'Deployment was interrupted and "
                "has been marked failed during migration.') "
                f"WHERE status IN ({DISPATCHABLE_STATUSES}) AND id NOT IN ("
                "  SELECT id FROM ("
                "    SELECT DISTINCT ON (app_id) id FROM deployments "
                f"    WHERE status IN ({DISPATCHABLE_STATUSES}) "
                "    ORDER BY app_id, created_at DESC"
                "  ) AS keep"
                ")"
            )
        )
    else:
        op.execute(
            sa.text(
                "UPDATE deployments SET status = 'failed' "
                f"WHERE status IN ({DISPATCHABLE_STATUSES}) AND id NOT IN ("
                "  SELECT MAX(id) FROM deployments "
                f"  WHERE status IN ({DISPATCHABLE_STATUSES}) GROUP BY app_id"
                ")"
            )
        )

    op.drop_index("uq_deployments_active_per_app", table_name="deployments")
    op.create_index(
        "uq_deployments_active_per_app",
        "deployments",
        ["app_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN ({DISPATCHABLE_STATUSES})"),
        sqlite_where=sa.text(f"status IN ({DISPATCHABLE_STATUSES})"),
    )

    # Same treatment for live commands: keep the newest per deployment.
    if _is_postgresql():
        op.execute(
            sa.text(
                "UPDATE deployment_commands SET status = 'failed', "
                "error_message = COALESCE(error_message, 'Duplicate command resolved "
                "during migration.') "
                f"WHERE status IN {ACTIVE_COMMAND_STATUSES} AND id NOT IN ("
                "  SELECT id FROM ("
                "    SELECT DISTINCT ON (deployment_id) id FROM deployment_commands "
                f"    WHERE status IN {ACTIVE_COMMAND_STATUSES} "
                "    ORDER BY deployment_id, created_at DESC"
                "  ) AS keep"
                ")"
            )
        )
    else:
        op.execute(
            sa.text(
                "UPDATE deployment_commands SET status = 'failed' "
                f"WHERE status IN {ACTIVE_COMMAND_STATUSES} AND id NOT IN ("
                "  SELECT MAX(id) FROM deployment_commands "
                f"  WHERE status IN {ACTIVE_COMMAND_STATUSES} GROUP BY deployment_id"
                ")"
            )
        )

    op.create_index(
        "uq_deployment_commands_active_per_deployment",
        "deployment_commands",
        ["deployment_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN {ACTIVE_COMMAND_STATUSES}"),
        sqlite_where=sa.text(f"status IN {ACTIVE_COMMAND_STATUSES}"),
    )


def downgrade() -> None:
    op.drop_index("uq_deployment_commands_active_per_deployment", table_name="deployment_commands")
    op.drop_index("uq_deployments_active_per_app", table_name="deployments")
    op.create_index(
        "uq_deployments_active_per_app",
        "deployments",
        ["app_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN {OLD_ACTIVE_STATUSES}"),
        sqlite_where=sa.text(f"status IN {OLD_ACTIVE_STATUSES}"),
    )
