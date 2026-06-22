"""add server public ssh key

Revision ID: 0003_add_server_public_ssh_key
Revises: 0002_add_deployment_kind
Create Date: 2026-06-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_add_server_public_ssh_key"
down_revision: Union[str, None] = "0002_add_deployment_kind"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("servers", sa.Column("public_ssh_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("servers", "public_ssh_key")
