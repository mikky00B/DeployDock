"""Ingestion of deployment events reported by agents (spec §20, §25).

Events flow: agent → POST /agents/{id}/events → this module → deployment_logs
rows + deployment status transitions → the existing SSE stream (the event bus
is notified on every write).

Ingestion is defensive by design:
- only events for deployments the agent holds a command for are accepted;
- terminal statuses are never overwritten (cancel must win over a racing
  agent result);
- unknown event types are logged as system lines instead of rejected, so an
  older/newer agent can still report;
- rejections are logged server-side and counted in the response — a
  systematically misbehaving agent must be visible.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Agent,
    App,
    AuditLog,
    Deployment,
    DeploymentCommand,
    DeploymentLog,
    DeploymentLogStream,
    User,
)
from app.models.deployment import (
    TERMINAL_DEPLOYMENT_STATUSES,
    DeploymentKind,
    DeploymentStatus,
)
from app.services.agent_dispatch import (
    dispatch_deployment,
    promote_next_queued_deployment,
)
from app.services.deployment_events import deployment_event_bus

logger = logging.getLogger("deploydock.agent_events")

STAGE_TO_STATUS = {
    "clone": DeploymentStatus.cloning,
    "build": DeploymentStatus.building,
    "test": DeploymentStatus.testing,
    "start": DeploymentStatus.deploying,
    "proxy": DeploymentStatus.deploying,
    "cleanup": DeploymentStatus.deploying,
    "health_check": DeploymentStatus.health_check,
}


class EventRejected(Exception):
    """The event cannot be applied (unknown deployment, terminal status)."""


async def ingest_events(
    session: AsyncSession,
    *,
    agent: Agent,
    events: list[dict],
) -> tuple[int, int]:
    """Apply a batch of agent events. Returns (accepted, rejected).

    The per-deployment log sequence is read once per deployment per batch and
    then allocated in memory — a several-hundred-line deploy log must not cost
    one max(sequence) query per line.
    """
    accepted = 0
    rejected = 0
    # deployment_id → (deployment, next log sequence)
    batch: dict[uuid.UUID, tuple[Deployment, int]] = {}

    for event in events:
        try:
            deployment = await _owned_deployment(session, agent=agent, event=event)
        except EventRejected as exc:
            logger.warning(
                "Rejected agent event from %s (%s): %s",
                agent.name,
                event.get("type"),
                exc,
            )
            rejected += 1
            continue

        if deployment.id not in batch:
            next_sequence = await _max_sequence(session, deployment.id)
            batch[deployment.id] = (deployment, next_sequence)

        stored_deployment, next_sequence = batch[deployment.id]
        handler = _HANDLERS.get(event.get("type"))
        if handler is None:
            allocate = _allocator(stored_deployment, batch)
            _add_log(
                session,
                stored_deployment,
                allocate,
                DeploymentLogStream.system,
                f"unhandled agent event type: {event.get('type')}",
            )
        else:
            await handler(
                session,
                deployment=stored_deployment,
                event=event,
                allocate=_allocator(stored_deployment, batch),
            )

        batch[deployment.id] = (stored_deployment, batch[deployment.id][1])
        accepted += 1

    await session.commit()
    for deployment_id in batch:
        deployment_event_bus.notify(deployment_id)
    return accepted, rejected


def _allocator(deployment: Deployment, batch: dict) -> Callable[[], int]:
    def allocate() -> int:
        stored, next_sequence = batch[deployment.id]
        batch[deployment.id] = (stored, next_sequence + 1)
        return next_sequence

    return allocate


async def _owned_deployment(session: AsyncSession, *, agent: Agent, event: dict) -> Deployment:
    deployment_id_text = event.get("deployment_id")
    if not deployment_id_text:
        raise EventRejected("event is missing deployment_id")
    try:
        deployment_id = uuid.UUID(str(deployment_id_text))
    except ValueError as exc:
        raise EventRejected("deployment_id is not a uuid") from exc

    result = await session.execute(
        select(Deployment)
        .join(DeploymentCommand, DeploymentCommand.deployment_id == Deployment.id)
        .where(
            Deployment.id == deployment_id,
            DeploymentCommand.agent_id == agent.id,
        )
        .limit(1)
    )
    deployment = result.scalar_one_or_none()
    if deployment is None:
        raise EventRejected(f"agent does not hold a command for deployment {deployment_id}")
    return deployment


async def _on_started(
    session: AsyncSession,
    *,
    deployment: Deployment,
    event: dict,
    allocate: Callable[[], int],
) -> None:
    if deployment.started_at is None:
        deployment.started_at = datetime.now(UTC)
    _add_log(session, deployment, allocate, DeploymentLogStream.system, "Agent picked up deployment")


async def _on_stage_started(
    session: AsyncSession,
    *,
    deployment: Deployment,
    event: dict,
    allocate: Callable[[], int],
) -> None:
    stage = str(event.get("stage", ""))
    status = STAGE_TO_STATUS.get(stage)
    if status is not None and deployment.status not in TERMINAL_DEPLOYMENT_STATUSES:
        deployment.status = status
    _add_log(session, deployment, allocate, DeploymentLogStream.system, f"Stage started: {stage}")


async def _on_stage_completed(
    session: AsyncSession,
    *,
    deployment: Deployment,
    event: dict,
    allocate: Callable[[], int],
) -> None:
    stage = str(event.get("stage", ""))
    _add_log(session, deployment, allocate, DeploymentLogStream.system, f"Stage completed: {stage}")


async def _on_log(
    session: AsyncSession,
    *,
    deployment: Deployment,
    event: dict,
    allocate: Callable[[], int],
) -> None:
    stream_name = str(event.get("stream", "stdout"))
    try:
        stream = DeploymentLogStream(stream_name)
    except ValueError:
        stream = DeploymentLogStream.stdout
    lines = event.get("lines")
    if isinstance(lines, list):
        for line in lines:
            _add_log(session, deployment, allocate, stream, str(line))
    elif event.get("line") is not None:
        _add_log(session, deployment, allocate, stream, str(event["line"]))


async def _on_health_check_passed(
    session: AsyncSession,
    *,
    deployment: Deployment,
    event: dict,
    allocate: Callable[[], int],
) -> None:
    deployment.healthcheck_status_code = event.get("status_code")
    deployment.healthcheck_ok = True
    deployment.healthcheck_error = None
    _add_log(
        session,
        deployment,
        allocate,
        DeploymentLogStream.system,
        f"Health check passed ({event.get('status_code')})",
    )


async def _on_health_check_failed(
    session: AsyncSession,
    *,
    deployment: Deployment,
    event: dict,
    allocate: Callable[[], int],
) -> None:
    deployment.healthcheck_status_code = event.get("status_code")
    deployment.healthcheck_ok = False
    deployment.healthcheck_error = str(event.get("error") or "health check failed")
    _add_log(
        session,
        deployment,
        allocate,
        DeploymentLogStream.system,
        f"Health check failed: {deployment.healthcheck_error}",
    )


async def _on_completed(
    session: AsyncSession,
    *,
    deployment: Deployment,
    event: dict,
    allocate: Callable[[], int],
) -> None:
    if deployment.status in TERMINAL_DEPLOYMENT_STATUSES:
        return  # cancel already won; do not resurrect
    commit_sha = event.get("commit_sha") or deployment.commit_sha
    deployment.status = DeploymentStatus.success
    deployment.commit_sha = commit_sha
    deployment.finished_at = datetime.now(UTC)
    deployment.exit_code = 0
    reported_duration = event.get("duration_seconds")
    if isinstance(reported_duration, int):
        # The agent measured the real wall-clock deploy; trust it over the
        # ingestion timestamp delta.
        deployment.duration_seconds = max(0, reported_duration)
    elif deployment.started_at is not None:
        deployment.duration_seconds = max(
            0,
            int((deployment.finished_at - _as_utc(deployment.started_at)).total_seconds()),
        )
    app = await session.get(App, deployment.app_id)
    if app is not None and commit_sha:
        app.current_commit = commit_sha
        app.last_successful_commit = commit_sha
    owner = await session.get(User, deployment.owner_id)
    await create_audit(
        session,
        owner=owner,
        action="deployment.succeeded",
        entity_id=deployment.id,
        metadata={"app_id": str(deployment.app_id), "commit_sha": commit_sha},
    )
    _add_log(session, deployment, allocate, DeploymentLogStream.system, "Deployment succeeded")
    promoted = await promote_next_queued_deployment(session, app_id=deployment.app_id)
    if promoted is not None:
        # Same app, therefore same server and same agent: re-arm the pipeline.
        await dispatch_deployment(session, deployment=promoted)


async def _on_failed(
    session: AsyncSession,
    *,
    deployment: Deployment,
    event: dict,
    allocate: Callable[[], int],
) -> None:
    if deployment.status in TERMINAL_DEPLOYMENT_STATUSES:
        return  # cancel already won; do not resurrect
    error = str(event.get("error") or "Deployment failed on agent")
    deployment.status = DeploymentStatus.failed
    deployment.error_message = error
    deployment.exit_code = event.get("exit_code") if isinstance(event.get("exit_code"), int) else 1
    deployment.finished_at = datetime.now(UTC)
    reported_duration = event.get("duration_seconds")
    if isinstance(reported_duration, int):
        deployment.duration_seconds = max(0, reported_duration)
    elif deployment.started_at is not None:
        deployment.duration_seconds = max(
            0,
            int((deployment.finished_at - _as_utc(deployment.started_at)).total_seconds()),
        )
    owner = await session.get(User, deployment.owner_id)
    await create_audit(
        session,
        owner=owner,
        action="deployment.failed",
        entity_id=deployment.id,
        metadata={"app_id": str(deployment.app_id), "error": error},
    )
    _add_log(session, deployment, allocate, DeploymentLogStream.system, f"Deployment failed: {error}")
    promoted = await promote_next_queued_deployment(session, app_id=deployment.app_id)
    if promoted is not None:
        await dispatch_deployment(session, deployment=promoted)


def _add_log(
    session: AsyncSession,
    deployment: Deployment,
    allocate: Callable[[], int],
    stream: DeploymentLogStream,
    line: str,
) -> None:
    if not line:
        return
    session.add(
        DeploymentLog(
            deployment_id=deployment.id,
            stream=stream,
            line=line,
            sequence=allocate(),
        )
    )


async def _max_sequence(session: AsyncSession, deployment_id: uuid.UUID) -> int:
    current = await session.scalar(
        select(func.max(DeploymentLog.sequence)).where(DeploymentLog.deployment_id == deployment_id)
    )
    return (current or 0) + 1


async def create_audit(
    session: AsyncSession,
    *,
    owner: User | None,
    action: str,
    entity_id: uuid.UUID,
    metadata: dict,
) -> None:
    if owner is None:
        return
    session.add(
        AuditLog(
            owner_id=owner.id,
            action=action,
            entity_type="deployment",
            entity_id=str(entity_id),
            metadata_json=metadata,
        )
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


_HANDLERS = {
    "deployment_started": _on_started,
    "stage_started": _on_stage_started,
    "stage_completed": _on_stage_completed,
    "log": _on_log,
    "health_check_passed": _on_health_check_passed,
    "health_check_failed": _on_health_check_failed,
    "deployment_completed": _on_completed,
    "deployment_failed": _on_failed,
}


def ensure_deployment_kind(kind: str) -> DeploymentKind:
    return DeploymentKind(kind)
