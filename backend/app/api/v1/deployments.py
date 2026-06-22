import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db_session, get_sessionmaker
from app.models import User
from app.schemas.deployment import DeploymentDetailRead, DeploymentRead
from app.schemas.deployment_log import DeploymentLogRead
from app.services.deployment_service import (
    create_deployment,
    create_rollback_deployment,
    get_deployment_for_user,
    list_deployment_logs,
    list_deployments_for_app,
)
from app.services.deployment_stream_service import stream_deployment_events
from app.services.ssh_service import SSHService, get_ssh_service
from app.workers.deployment_runner import DeploymentRunner

router = APIRouter(tags=["deployments"])


def get_deployment_runner(
    sessionmaker: Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)],
    settings: Annotated[Settings, Depends(get_settings)],
    ssh_service: Annotated[SSHService, Depends(get_ssh_service)],
) -> DeploymentRunner:
    return DeploymentRunner(sessionmaker=sessionmaker, settings=settings, ssh_service=ssh_service)


@router.post("/apps/{app_id}/deploy", response_model=DeploymentRead, status_code=status.HTTP_202_ACCEPTED)
async def deploy_app(
    app_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    runner: Annotated[DeploymentRunner, Depends(get_deployment_runner)],
) -> DeploymentRead:
    deployment = await create_deployment(session, app_id=app_id, current_user=current_user)
    background_tasks.add_task(runner.run, deployment.id)
    return DeploymentRead.model_validate(deployment)


@router.get("/apps/{app_id}/deployments", response_model=list[DeploymentRead])
async def app_deployments(
    app_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[DeploymentRead]:
    deployments = await list_deployments_for_app(session, app_id=app_id, current_user=current_user)
    return [DeploymentRead.model_validate(deployment) for deployment in deployments]


@router.get("/deployments/{deployment_id}", response_model=DeploymentDetailRead)
async def show_deployment(
    deployment_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DeploymentDetailRead:
    deployment = await get_deployment_for_user(
        session,
        deployment_id=deployment_id,
        current_user=current_user,
        include_logs=True,
    )
    return DeploymentDetailRead.model_validate(deployment)


@router.get("/deployments/{deployment_id}/logs", response_model=list[DeploymentLogRead])
async def deployment_logs(
    deployment_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[DeploymentLogRead]:
    return await list_deployment_logs(session, deployment_id=deployment_id, current_user=current_user)


@router.get("/deployments/{deployment_id}/stream")
async def deployment_log_stream(
    deployment_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    sessionmaker: Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)],
) -> StreamingResponse:
    await get_deployment_for_user(session, deployment_id=deployment_id, current_user=current_user)
    return StreamingResponse(
        stream_deployment_events(
            sessionmaker=sessionmaker,
            deployment_id=deployment_id,
            owner_id=current_user.id,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/deployments/{deployment_id}/rollback", response_model=DeploymentRead, status_code=status.HTTP_202_ACCEPTED)
async def rollback_deployment(
    deployment_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    runner: Annotated[DeploymentRunner, Depends(get_deployment_runner)],
) -> DeploymentRead:
    rollback_record = await create_rollback_deployment(
        session,
        deployment_id=deployment_id,
        current_user=current_user,
    )
    background_tasks.add_task(runner.run_rollback, rollback_record.id)
    return DeploymentRead.model_validate(rollback_record)
