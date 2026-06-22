import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Deployment, DeploymentLog, User
from app.models.deployment import DeploymentKind, DeploymentStatus
from app.schemas.deployment_log import DeploymentLogRead
from app.services.audit_service import create_audit_log
from app.services.app_service import get_app_for_user


async def create_deployment(
    session: AsyncSession,
    *,
    app_id: uuid.UUID,
    current_user: User,
) -> Deployment:
    app = await get_app_for_user(session, app_id=app_id, current_user=current_user)
    deployment = Deployment(
        owner_id=current_user.id,
        app_id=app.id,
        server_id=app.server_id,
        status=DeploymentStatus.pending,
        kind=DeploymentKind.deploy,
        triggered_by=current_user.email,
    )
    session.add(deployment)
    await session.flush()
    await create_audit_log(
        session,
        current_user=current_user,
        action="deployment.started",
        entity_type="deployment",
        entity_id=deployment.id,
        metadata={"app_id": str(app.id), "kind": DeploymentKind.deploy.value},
    )
    await session.commit()
    await session.refresh(deployment)
    return deployment


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
    target_commit = await find_previous_successful_commit(
        session,
        source_deployment=source_deployment,
        current_user=current_user,
    )
    if target_commit is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No previous successful deployment commit is available for rollback",
        )

    app = await get_app_for_user(session, app_id=source_deployment.app_id, current_user=current_user)
    if app.restart_command is None and app.service_name is None:
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
        triggered_by=current_user.email,
    )
    session.add(rollback_deployment)
    await session.flush()
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
        },
    )
    await session.commit()
    await session.refresh(rollback_deployment)
    return rollback_deployment


async def find_previous_successful_commit(
    session: AsyncSession,
    *,
    source_deployment: Deployment,
    current_user: User,
) -> str | None:
    result = await session.execute(
        select(Deployment.commit_sha)
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
