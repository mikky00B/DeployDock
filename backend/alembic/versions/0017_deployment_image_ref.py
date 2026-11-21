"""retain the built image per deployment for deterministic rollback (audit H4)

Revision ID: 0017_deployment_image_ref
Revises: 0016_deployment_last_progress_at
Create Date: 2026-11-21

A rollback that rebuilds from mutable source is not a rollback: the base
image tag may have moved, dependencies may have been yanked, and the commit
may be gone after a force-push. The agent now tags the image it built with
the deployment id, reports the ref on completion, and a rollback re-runs the
retained image without clone/build.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_deployment_image_ref"
down_revision: str | None = "0016_deployment_last_progress_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "deployments",
        sa.Column("image_ref", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("deployments", "image_ref")
