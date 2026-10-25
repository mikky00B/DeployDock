"""email verification codes

Revision ID: 0013_email_verification
Revises: 0012_concurrency_guards
Create Date: 2026-10-01

Adds email verification to the auth flow (modern signup):

- users.email_verified / users.email_verified_at: whether the address has
  been confirmed with a code;
- email_verification_codes: hashed 6-digit codes with an expiry, an attempt
  counter, and consumption — one row per sent code, newest wins.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_email_verification"
down_revision: str | None = "0012_concurrency_guards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_email_verified", "users", ["email_verified"])

    # Existing accounts predate the verification feature and must keep working:
    # only accounts created AFTER this migration prove their address with a code.
    op.execute("UPDATE users SET email_verified = true")

    op.create_table(
        "email_verification_codes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False, server_default="signup"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_email_verification_codes_user_id", "email_verification_codes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_email_verification_codes_user_id", table_name="email_verification_codes")
    op.drop_table("email_verification_codes")
    op.drop_index("ix_users_email_verified", table_name="users")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email_verified")
