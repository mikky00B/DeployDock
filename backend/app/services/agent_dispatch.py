"""Command queue between the control plane and agents (spec §15, §25).

FastAPI decides *what* should happen: every deployment that targets a server
with a registered agent becomes a self-contained command the agent claims by
polling. The agent never queries for context — the payload embeds everything
needed to execute (spec §77 criterion 17).
"""

import logging
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Agent,
    AgentCommandKind,
    AgentCommandStatus,
    App,
    AuditLog,
    Deployment,
    DeploymentCommand,
    DeploymentLog,
    DeploymentLogStream,
    User,
)
from app.models.deployment import (
    DISPATCHABLE_DEPLOYMENT_STATUSES,
    TERMINAL_DEPLOYMENT_STATUSES,
    DeploymentKind,
    DeploymentStatus,
)

logger = logging.getLogger("deploydock.agent_dispatch")


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
) -> bool:
    """Enqueue a command for the agent. False when one is already live.

    The partial unique index on (deployment_id) for queued/claimed commands is
    the authority: two dispatch calls racing (webhook vs promotion) resolve to
    a single command at the database, not in application code.
    """
    command = DeploymentCommand(
        agent_id=agent.id,
        deployment_id=deployment.id,
        kind=AgentCommandKind.rollback
        if deployment.kind is DeploymentKind.rollback
        else AgentCommandKind.deploy,
        payload=build_command_payload(app, deployment),
    )
    deployment_id = deployment.id
    session.add(command)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        logger.info(
            "Deployment %s already has a live command; skipping duplicate dispatch",
            deployment_id,
        )
        return False
    return True


async def dispatch_deployment(session: AsyncSession, *, deployment: Deployment) -> bool:
    """Route a deployment to its server's agent. True when enqueued (or when a
    live command already exists for it).

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
    enqueued = await enqueue_deployment_command(session, agent=agent, deployment=deployment, app=app)
    await session.commit()
    return enqueued or True


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


async def reclaim_stale_commands(session: AsyncSession, *, lease_seconds: int) -> int:
    """Reclaim commands whose agent lease expired (spec §2.5 gap fix).

    An agent that claims a command and then dies (OOM, kill -9, network
    partition) would otherwise leave the command claimed and the deployment in
    a pipeline stage forever, blocking the app's next deploy. Expired claims
    fail the command and its deployment (unless already terminal), then the
    queue promotion runs so a waiting deployment can proceed.

    Called from the startup sweep and a periodic background task in main.py.
    """
    from app.services.deployment_events import deployment_event_bus

    cutoff = datetime.now(UTC) - timedelta(seconds=lease_seconds)
    result = await session.execute(
        select(DeploymentCommand)
        .where(
            DeploymentCommand.status == AgentCommandStatus.claimed,
            DeploymentCommand.claimed_at <= cutoff,
        )
    )
    stale = list(result.scalars().all())
    if not stale:
        return 0

    affected_app_ids: set[uuid.UUID] = set()
    notified_deployments: list[uuid.UUID] = []
    for command in stale:
        command.status = AgentCommandStatus.failed
        command.error_message = "Agent lease expired; the agent never reported a result."
        command.completed_at = datetime.now(UTC)

        deployment = await session.get(Deployment, command.deployment_id)
        if deployment is None:
            continue
        if deployment.status not in TERMINAL_DEPLOYMENT_STATUSES:
            deployment.status = DeploymentStatus.failed
            deployment.error_message = (
                "The agent stopped responding during this deployment and the "
                "command lease expired. It has been marked failed automatically."
            )
            deployment.finished_at = datetime.now(UTC)
            if deployment.started_at is not None:
                deployment.duration_seconds = max(
                    0,
                    int((deployment.finished_at - _as_utc(deployment.started_at)).total_seconds()),
                )
            owner = await session.get(User, deployment.owner_id)
            if owner is not None:
                session.add(
                    AuditLog(
                        owner_id=owner.id,
                        action="deployment.failed",
                        entity_type="deployment",
                        entity_id=str(deployment.id),
                        metadata_json={
                            "app_id": str(deployment.app_id),
                            "error": "agent command lease expired",
                        },
                    )
                )
            session.add(
                DeploymentLog(
                    deployment_id=deployment.id,
                    stream=DeploymentLogStream.system,
                    line="Agent lease expired; deployment marked failed",
                    sequence=await _next_sequence(session, deployment.id),
                )
            )
            affected_app_ids.add(deployment.app_id)
        notified_deployments.append(deployment.id)

    await session.commit()
    for deployment_id in notified_deployments:
        deployment_event_bus.notify(deployment_id)
    for app_id in affected_app_ids:
        promoted = await promote_next_queued_deployment(session, app_id=app_id)
        if promoted is not None:
            await dispatch_deployment(session, deployment=promoted)

    logger.warning("Reclaimed %s expired agent command(s)", len(stale))
    return len(stale)


async def _next_sequence(session: AsyncSession, deployment_id: uuid.UUID) -> int:
    from sqlalchemy import func

    from app.models import DeploymentLog

    current = await session.scalar(
        select(func.max(DeploymentLog.sequence)).where(DeploymentLog.deployment_id == deployment_id)
    )
    return (current or 0) + 1


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


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
