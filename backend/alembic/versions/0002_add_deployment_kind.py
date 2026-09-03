"""add deployment kind

Revision ID: 0002_add_deployment_kind
Revises: 0001_create_core_tables
Create Date: 2026-06-21

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_add_deployment_kind"
down_revision: str | None = "0001_create_core_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "deployments",
        sa.Column(
            "kind",
            sa.Enum("deploy", "rollback", name="deploymentkind", native_enum=False),
            server_default="deploy",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("deployments", "kind")
