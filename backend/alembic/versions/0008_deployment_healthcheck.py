"""add deployment healthcheck result columns

Revision ID: 0008_deployment_healthcheck
Revises: 0007_deployment_status_pipeline
Create Date: 2026-09-04

Integrated from a stray migration dropped into this directory as
"0004_add_deployment_healthcheck_result.py" (it collided with the committed
0004 and forked the migration chain into two heads). Content is unchanged
apart from renumbering onto the single chain and adopting house style.

The revision id is deliberately 27 characters: alembic_version.version_num is
VARCHAR(32), and the previous id ("0008_deployment_healthcheck_result", 34
characters) exceeded it — SQLite ignores varchar lengths, so tests passed
while every real PostgreSQL database failed at this step.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_deployment_healthcheck"
down_revision: str | None = "0007_deployment_status_pipeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("deployments", sa.Column("healthcheck_url", sa.String(length=500), nullable=True))
    op.add_column("deployments", sa.Column("healthcheck_status_code", sa.Integer(), nullable=True))
    op.add_column("deployments", sa.Column("healthcheck_ok", sa.Boolean(), nullable=True))
    op.add_column("deployments", sa.Column("healthcheck_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("deployments", "healthcheck_error")
    op.drop_column("deployments", "healthcheck_ok")
    op.drop_column("deployments", "healthcheck_status_code")
    op.drop_column("deployments", "healthcheck_url")
