"""Command queue between the control plane and agents (spec §15, §25).

FastAPI decides *what* should happen: every deployment that targets a server
with a registered agent becomes a self-contained command the agent claims by
polling. The agent never queries for context — the payload embeds everything
needed to execute (spec §77 criterion 17).
"""

import re
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Agent,
    AgentCommandKind,
    AgentCommandStatus,
    App,
    Deployment,
    DeploymentCommand,
)
from app.models.deployment import DeploymentKind


def slugify_container_base(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    return slug or "app"


def container_base_for(app_name: str) -> str:
    return f"deploydock-{slugify_container_base(app_name)}"


def build_command_payload(app: App, deployment: Deployment) -> dict:
    """Self-contained deployment spec sent to the agent."""
    return {
        "deployment_id": str(deployment.id),
        "kind": deployment.kind.value,
        "commit_sha": deployment.commit_sha,
        "app": {
            "name": app.name,
            "repository_url": app.repository_url,
            "branch": app.branch,
            "app_path": app.app_path,
            "port": app.port,
            "healthcheck_url": app.healthcheck_url,
            "container_base": container_base_for(app.name),
            "cpu_limit": app.cpu_limit,
            "memory_limit": app.memory_limit,
        },
    }


async def find_agent_for_server(session: AsyncSession, *, server_id: uuid.UUID) -> Agent | None:
    result = await session.execute(
        select(Agent)
        .where(
            Agent.server_id == server_id,
            Agent.reported_status == "active",
            Agent.revoked_at.is_(None),
        )
        .order_by(Agent.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def enqueue_deployment_command(
    session: AsyncSession,
    *,
    agent: Agent,
    deployment: Deployment,
    app: App,
) -> DeploymentCommand:
    command = DeploymentCommand(
        agent_id=agent.id,
        deployment_id=deployment.id,
        kind=AgentCommandKind.rollback
        if deployment.kind is DeploymentKind.rollback
        else AgentCommandKind.deploy,
        payload=build_command_payload(app, deployment),
    )
    session.add(command)
    await session.flush()
    return command


async def dispatch_deployment(session: AsyncSession, *, deployment: Deployment) -> bool:
    """Route a deployment to its server's agent. True when enqueued.

    Returns False when the server has no active agent, so the caller can fall
    back to the SSH bridge runner (spec §8: keep the old path until the agent
    replaces it).
    """
    app = await session.get(App, deployment.app_id)
    if app is None:
        return False
    agent = await find_agent_for_server(session, server_id=deployment.server_id)
    if agent is None:
        return False
    await enqueue_deployment_command(session, agent=agent, deployment=deployment, app=app)
    await session.commit()
    return True


async def claim_next_command(
    session: AsyncSession,
    *,
    agent: Agent,
) -> tuple[DeploymentCommand, str] | None:
    """Atomically claim the agent's oldest queued command.

    SELECT-then-conditional-UPDATE (instead of UPDATE..RETURNING) keeps this
    portable across PostgreSQL and SQLite; the rowcount check makes it safe
    when two pollers race for the same row.
    """
    while True:
        result = await session.execute(
            select(DeploymentCommand)
            .where(
                DeploymentCommand.agent_id == agent.id,
                DeploymentCommand.status == AgentCommandStatus.queued,
            )
            .order_by(DeploymentCommand.created_at.asc())
            .limit(1)
        )
        command = result.scalar_one_or_none()
        if command is None:
            return None

        claim_token = secrets.token_urlsafe(24)
        claimed = await session.execute(
            update(DeploymentCommand)
            .where(
                DeploymentCommand.id == command.id,
                DeploymentCommand.status == AgentCommandStatus.queued,
            )
            .values(
                status=AgentCommandStatus.claimed,
                claim_token=claim_token,
                claimed_at=datetime.now(UTC),
            )
        )
        if claimed.rowcount == 1:
            await session.commit()
            await session.refresh(command)
            return command, claim_token
        # Another poller won the race; loop to try the next queued row.
        await session.rollback()


async def complete_command(
    session: AsyncSession,
    *,
    agent: Agent,
    command_id: uuid.UUID,
    claim_token: str,
    succeeded: bool,
    error_message: str | None,
) -> DeploymentCommand | None:
    """Close out a claimed command. Returns None when the command does not
    belong to this agent or the claim token does not match."""
    command = await session.get(DeploymentCommand, command_id)
    if command is None or command.agent_id != agent.id:
        return None
    if command.status is not AgentCommandStatus.claimed or command.claim_token != claim_token:
        return None

    command.status = (
        AgentCommandStatus.completed if succeeded else AgentCommandStatus.failed
    )
    command.completed_at = datetime.now(UTC)
    command.error_message = error_message
    await session.commit()
    await session.refresh(command)
    return command


async def get_owned_deployment_for_agent(
    session: AsyncSession,
    *,
    agent: Agent,
    deployment_id: uuid.UUID,
) -> Deployment | None:
    """The deployment an agent may report on: one whose command it holds."""
    result = await session.execute(
        select(Deployment)
        .join(DeploymentCommand, DeploymentCommand.deployment_id == Deployment.id)
        .where(
            DeploymentCommand.agent_id == agent.id,
            Deployment.id == deployment_id,
            DeploymentCommand.status.in_(
                (AgentCommandStatus.claimed, AgentCommandStatus.completed)
            ),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def promote_next_queued_deployment(
    session: AsyncSession,
    *,
    app_id: uuid.UUID,
) -> Deployment | None:
    """Promote the app's oldest queued deployment to pending (spec §42).

    Called whenever a deployment reaches a terminal state. Returns the
    promoted deployment so the caller can dispatch it; the one-active-per-app
    guard is re-checked here because queued rows are exempt from the partial
    unique index.
    """
    from app.models.deployment import (
        DISPATCHABLE_DEPLOYMENT_STATUSES,
        DeploymentStatus,
    )

    active = await session.execute(
        select(Deployment.id)
        .where(
            Deployment.app_id == app_id,
            Deployment.status.in_(DISPATCHABLE_DEPLOYMENT_STATUSES),
        )
        .limit(1)
    )
    if active.scalar_one_or_none() is not None:
        return None

    result = await session.execute(
        select(Deployment)
        .where(Deployment.app_id == app_id, Deployment.status == DeploymentStatus.queued)
        .order_by(Deployment.created_at.asc())
        .limit(1)
    )
    promoted = result.scalar_one_or_none()
    if promoted is None:
        return None

    promoted.status = DeploymentStatus.pending
    await session.commit()
    await session.refresh(promoted)
    return promoted
