import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Deployment, DeploymentLog, User
from app.models.deployment import (
    ACTIVE_DEPLOYMENT_STATUSES,
    DISPATCHABLE_DEPLOYMENT_STATUSES,
    TERMINAL_DEPLOYMENT_STATUSES,
    DeploymentKind,
    DeploymentStatus,
)
from app.schemas.deployment_log import DeploymentLogRead
from app.services.app_service import get_app_for_user
from app.services.audit_service import create_audit_log
from app.services.deployment_events import deployment_event_bus
from app.services.email_service import notify_deployment_result


async def get_active_deployment(session: AsyncSession, *, app_id: uuid.UUID) -> Deployment | None:
    """Return the app's in-flight deployment, if any.

    Checked across all owners of the app, not just the caller: two concurrent
    deployments would race on the same checkout on the target server regardless
    of who triggered them.
    """
    result = await session.execute(
        select(Deployment)
        .where(
            Deployment.app_id == app_id,
            Deployment.status.in_(ACTIVE_DEPLOYMENT_STATUSES),
        )
        .order_by(Deployment.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _guard_against_concurrent_deployment(session: AsyncSession, *, app_id: uuid.UUID) -> None:
    active = await get_active_deployment(session, app_id=app_id)
    if active is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Deployment {active.id} is already {active.status.value} for this app. "
                "Wait for it to finish before starting another."
            ),
        )


async def create_deployment(
    session: AsyncSession,
    *,
    app_id: uuid.UUID,
    current_user: User,
    queue_if_active: bool = False,
    commit_message: str | None = None,
) -> Deployment:
    """Create a deployment, optionally queueing behind an active one (spec §42).

    Interactive deploys keep the strict 409 contract against *running*
    deployments; automatic deploys (GitHub webhooks) set ``queue_if_active``
    so two quick pushes queue the second instead of failing it. Queued
    deployments are promoted by ``promote_next_queued_deployment`` when the
    active one turns terminal.

    A deployment created while another is already **queued** supersedes the
    older queued row (v3 §4.3): stale code must not run, so the newer
    deployment takes the queue slot and the old one goes terminal.
    """
    app = await get_app_for_user(session, app_id=app_id, current_user=current_user)
    active = await get_active_deployment(session, app_id=app.id)
    superseded: Deployment | None = None
    if active is not None:
        if active.status is not DeploymentStatus.queued:
            if not queue_if_active:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Deployment {active.id} is already {active.status.value} for this app. "
                        "Wait for it to finish before starting another."
                    ),
                )
        else:
            # A queued row exists: the new deployment replaces it (v3 §4.3 —
            # stale code must not run). Anything still dispatchable keeps the
            # slot, and an interactive caller facing a real deploy in flight
            # is refused *before* any mutation is staged.
            queued_row = active
            active = await _get_dispatchable_deployment(session, app_id=app.id)
            if active is not None and not queue_if_active:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Deployment {active.id} is already {active.status.value} for this app "
                        f"and deployment {queued_row.id} is queued. Wait for them to finish."
                    ),
                )
            superseded = queued_row
            # Any other queued row (a race the unique index now prevents, but
            # be thorough) goes superseded too: stale code must not run.
            await session.execute(
                update(Deployment)
                .where(
                    Deployment.app_id == app.id,
                    Deployment.status == DeploymentStatus.queued,
                    Deployment.id != queued_row.id,
                )
                .values(
                    status=DeploymentStatus.superseded,
                    finished_at=datetime.now(UTC),
                )
            )

    if superseded is not None:
        superseded.status = DeploymentStatus.superseded
        superseded.finished_at = datetime.now(UTC)
        await create_audit_log(
            session,
            current_user=current_user,
            action="deployment.superseded",
            entity_type="deployment",
            entity_id=superseded.id,
            metadata={"app_id": str(app.id)},
        )
        # Anything still dispatchable keeps the slot: the new deployment
        # queues behind it instead of starting immediately.
        active = await _get_dispatchable_deployment(session, app_id=app.id)
    deployment = Deployment(
        owner_id=current_user.id,
        app_id=app.id,
        server_id=app.server_id,
        status=DeploymentStatus.queued if active is not None else DeploymentStatus.pending,
        kind=DeploymentKind.deploy,
        commit_sha=None,
        commit_message=commit_message,
        triggered_by=current_user.email,
    )
    session.add(deployment)
    try:
        await session.flush()
    except IntegrityError as exc:
        # The partial unique index on (app_id) for non-terminal deployments is the
        # authoritative guard: it also catches races between two API workers.
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another deployment for this app started at the same time. Try again shortly.",
        ) from exc
    await create_audit_log(
        session,
        current_user=current_user,
        action="deployment.started",
        entity_type="deployment",
        entity_id=deployment.id,
        metadata={"app_id": str(app.id), "kind": DeploymentKind.deploy.value},
    )
    await session.commit()
    if superseded is not None:
        deployment_event_bus.notify(superseded.id)
    await session.refresh(deployment)
    return deployment


async def _get_dispatchable_deployment(
    session: AsyncSession, *, app_id: uuid.UUID
) -> Deployment | None:
    """The app's in-flight deployment that occupies the dispatch slot, if any
    (every active status except ``queued``)."""
    result = await session.execute(
        select(Deployment)
        .where(
            Deployment.app_id == app_id,
            Deployment.status.in_(DISPATCHABLE_DEPLOYMENT_STATUSES),
        )
        .order_by(Deployment.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_deployments_for_app(
    session: AsyncSession,
    *,
    app_id: uuid.UUID,
    current_user: User,
) -> list[Deployment]:
    await get_app_for_user(session, app_id=app_id, current_user=current_user)
    result = await session.execute(
        select(Deployment)
        .where(Deployment.app_id == app_id, Deployment.owner_id == current_user.id)
        .order_by(Deployment.created_at.desc())
    )
    return list(result.scalars().all())


async def get_deployment_for_user(
    session: AsyncSession,
    *,
    deployment_id: uuid.UUID,
    current_user: User,
    include_logs: bool = False,
) -> Deployment:
    query = select(Deployment).where(
        Deployment.id == deployment_id,
        Deployment.owner_id == current_user.id,
    )
    if include_logs:
        query = query.options(selectinload(Deployment.logs))

    result = await session.execute(query)
    deployment = result.scalar_one_or_none()
    if deployment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found")
    return deployment


async def cancel_deployment(
    session: AsyncSession,
    *,
    deployment_id: uuid.UUID,
    current_user: User,
) -> Deployment:
    """Request cancellation of a non-terminal deployment (spec §46).

    The in-process runner cannot be interrupted mid-SSH-call, so this flips the
    row to ``canceled`` immediately and the runner honours it at its next
    checkpoint (before starting and after the current command returns).

    Canceling is idempotent while the row is ``canceled`` (a second request
    returns the row unchanged, no duplicate audit entry), while every other
    terminal status is immutable and answers 409.
    """
    deployment = await get_deployment_for_user(
        session,
        deployment_id=deployment_id,
        current_user=current_user,
    )
    if deployment.status is DeploymentStatus.canceled:
        # Idempotent no-op: the row is already terminal, just not immutable.
        return deployment
    if deployment.status in TERMINAL_DEPLOYMENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Deployment {deployment.id} is already {deployment.status.value} and cannot be canceled",
        )

    deployment.status = DeploymentStatus.canceled
    deployment.finished_at = datetime.now(UTC)
    if deployment.started_at is not None:
        deployment.duration_seconds = max(
            0, int((deployment.finished_at - _as_utc(deployment.started_at)).total_seconds())
        )
    await create_audit_log(
        session,
        current_user=current_user,
        action="deployment.canceled",
        entity_type="deployment",
        entity_id=deployment.id,
        metadata={"app_id": str(deployment.app_id)},
    )
    await session.commit()
    await session.refresh(deployment)
    deployment_event_bus.notify(deployment.id)
    return deployment


async def list_deployment_logs(
    session: AsyncSession,
    *,
    deployment_id: uuid.UUID,
    current_user: User,
) -> list[DeploymentLogRead]:
    await get_deployment_for_user(session, deployment_id=deployment_id, current_user=current_user)
    result = await session.execute(
        select(DeploymentLog)
        .where(DeploymentLog.deployment_id == deployment_id)
        .order_by(DeploymentLog.sequence.asc())
    )
    return [DeploymentLogRead.model_validate(log) for log in result.scalars().all()]


async def create_rollback_deployment(
    session: AsyncSession,
    *,
    deployment_id: uuid.UUID,
    current_user: User,
) -> Deployment:
    source_deployment = await get_deployment_for_user(
        session,
        deployment_id=deployment_id,
        current_user=current_user,
    )
    # Checked before anything else: a rollback while a deploy is in flight would
    # fight over the same checkout.
    await _guard_against_concurrent_deployment(session, app_id=source_deployment.app_id)
    target = await find_previous_successful_deployment(
        session,
        source_deployment=source_deployment,
        current_user=current_user,
    )
    if target is None or target.commit_sha is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No previous successful deployment commit is available for rollback",
        )
    target_commit = target.commit_sha

    from app.services.agent_dispatch import find_agent_for_server

    app = await get_app_for_user(session, app_id=source_deployment.app_id, current_user=current_user)
    # The restart gate only applies to the SSH bridge, which restarts a systemd
    # service; an agent deployment rolls back as its own Docker cutover, with
    # no systemd involvement (audit H4).
    agent = await find_agent_for_server(
        session, server_id=source_deployment.server_id, owner_id=source_deployment.owner_id
    )
    if agent is None and app.restart_command is None and app.service_name is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="App does not have a restart command or service name",
        )

    rollback_deployment = Deployment(
        owner_id=current_user.id,
        app_id=source_deployment.app_id,
        server_id=source_deployment.server_id,
        status=DeploymentStatus.pending,
        kind=DeploymentKind.rollback,
        commit_sha=target_commit,
        previous_commit_sha=source_deployment.commit_sha,
        # The retained image of the successful deployment we are rolling back
        # to, when the agent built one (audit H4): the agent re-runs this image
        # instead of rebuilding from mutable source.
        image_ref=target.image_ref,
        triggered_by=current_user.email,
    )
    session.add(rollback_deployment)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another deployment for this app started at the same time. Try again shortly.",
        ) from exc
    await create_audit_log(
        session,
        current_user=current_user,
        action="rollback.started",
        entity_type="deployment",
        entity_id=rollback_deployment.id,
        metadata={
            "source_deployment_id": str(source_deployment.id),
            "app_id": str(source_deployment.app_id),
            "target_commit": target_commit,
            "image_ref": target.image_ref,
        },
    )
    await session.commit()
    await session.refresh(rollback_deployment)
    return rollback_deployment


async def find_previous_successful_deployment(
    session: AsyncSession,
    *,
    source_deployment: Deployment,
    current_user: User,
) -> Deployment | None:
    """The deployment to roll back to: the newest success strictly before the
    source, with its retained image so the rollback can reuse the artifact."""
    result = await session.execute(
        select(Deployment)
        .where(
            Deployment.owner_id == current_user.id,
            Deployment.app_id == source_deployment.app_id,
            Deployment.status == DeploymentStatus.success,
            Deployment.commit_sha.is_not(None),
            Deployment.id != source_deployment.id,
            Deployment.created_at <= source_deployment.created_at,
        )
        .order_by(Deployment.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def fail_orphaned_deployments(
    session: AsyncSession,
    *,
    older_than_seconds: int,
) -> int:
    """Mark deployments stuck without progress as failed, and finish the
    transition properly (audit H6).

    A deploy runs inside the API process, so a restart, crash, or worker recycle
    mid-deploy leaves the row non-terminal forever — blocking every later deploy
    of that app via the concurrency guard. This sweep reclaims them, and unlike
    a bare status flip it also notifies the SSE stream, sends the failure email,
    and promotes whatever was queued behind the reclaimed row.

    Rows are aged out from ``last_progress_at`` (falling back to ``created_at``),
    not ``created_at`` itself: a healthy long build keeps making observable
    progress and is never swept.
    """
    from app.services.agent_dispatch import dispatch_deployment, promote_next_queued_deployment

    cutoff = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
    result = await session.execute(
        select(Deployment).where(
            Deployment.status.in_(ACTIVE_DEPLOYMENT_STATUSES),
            func.coalesce(Deployment.last_progress_at, Deployment.created_at) <= cutoff,
        )
    )
    orphaned = list(result.scalars().all())
    if not orphaned:
        return 0

    affected_apps: set[uuid.UUID] = set()
    for deployment in orphaned:
        deployment.status = DeploymentStatus.failed
        deployment.error_message = (
            "Deployment was interrupted (the API process stopped while it was running) "
            "and has been marked failed automatically."
        )
        deployment.finished_at = datetime.now(UTC)
        if deployment.started_at is not None:
            deployment.duration_seconds = max(
                0, int((deployment.finished_at - _as_utc(deployment.started_at)).total_seconds())
            )
        affected_apps.add(deployment.app_id)

    await session.commit()
    for deployment in orphaned:
        deployment_event_bus.notify(deployment.id)
        with suppress(Exception):  # noqa: BLE001 - email must not break the sweep
            await notify_deployment_result(session, deployment_id=deployment.id)
    for app_id in affected_apps:
        promoted = await promote_next_queued_deployment(session, app_id=app_id)
        if promoted is not None:
            await dispatch_deployment(session, deployment=promoted)
    return len(orphaned)


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
