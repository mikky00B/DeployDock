"""one active agent per server (audit C1/H3)

Revision ID: 0015_agent_tenant_isolation
Revises: 0014_superseded_deployment_status
Create Date: 2026-11-21

Two agent-plane trust fixes:

1. The dispatch path now verifies that the agent's server belongs to the
   deployment owner (service-layer change), so an agent registered against
   another tenant's server id can no longer receive that tenant's commands
   and decrypted environment variables.

2. A partial unique index enforces at most one active agent per server.
   Registration supersedes the previous agent; before creating the index any
   duplicate active rows are revoked, keeping the newest per server, so a
   stale reinstall can never shadow the live agent.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_agent_tenant_isolation"
down_revision: str | None = "0014_superseded_deployment_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE_AGENT_PREDICATE = "revoked_at IS NULL AND reported_status = 'active'"


def _bind() -> sa.engine.Connection:
    return op.get_bind()


def _is_postgresql() -> bool:
    return _bind().dialect.name == "postgresql"


def upgrade() -> None:
    # Revoke duplicate active agents per server, keeping the newest. A server
    # rebuilt without cleaning the old agent row would otherwise violate the
    # new index — and the old row is precisely the stale one the fix targets.
    if _is_postgresql():
        op.execute(
            sa.text(
                "UPDATE agents SET revoked_at = now(), reported_status = 'retired' "
                f"WHERE {ACTIVE_AGENT_PREDICATE} AND server_id IS NOT NULL AND id NOT IN ("
                "  SELECT id FROM ("
                "    SELECT DISTINCT ON (server_id) id FROM agents "
                f"    WHERE {ACTIVE_AGENT_PREDICATE} AND server_id IS NOT NULL "
                "    ORDER BY server_id, created_at DESC"
                "  ) AS keep"
                ")"
            )
        )
    else:
        op.execute(
            sa.text(
                "UPDATE agents SET revoked_at = CURRENT_TIMESTAMP, reported_status = 'retired' "
                f"WHERE {ACTIVE_AGENT_PREDICATE} AND server_id IS NOT NULL AND id NOT IN ("
                "  SELECT id FROM agents a WHERE "
                f"  {ACTIVE_AGENT_PREDICATE.replace('reported_status', 'a.reported_status').replace('revoked_at', 'a.revoked_at')} "
                "  AND a.server_id IS NOT NULL AND a.id IN ("
                "    SELECT id FROM (SELECT id, MAX(created_at) FROM agents "
                "    WHERE server_id IS NOT NULL GROUP BY server_id)"
                "  )"
                ")"
            )
        )

    op.create_index(
        "uq_agents_active_server",
        "agents",
        ["server_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE_AGENT_PREDICATE),
        sqlite_where=sa.text(ACTIVE_AGENT_PREDICATE),
    )


def downgrade() -> None:
    op.drop_index("uq_agents_active_server", table_name="agents")
