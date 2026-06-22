import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models import User
from app.schemas.app import (
    AppCreate,
    AppRead,
    AppServiceLogsRead,
    AppServiceRestartRead,
    AppServiceStatusRead,
    AppUpdate,
)
from app.services.app_service import (
    check_app_service_status,
    create_app,
    delete_app,
    get_app_service_logs,
    get_app_for_user,
    list_apps,
    restart_app_service,
    update_app,
)
from app.services.ssh_service import SSHService, get_ssh_service

router = APIRouter(prefix="/apps", tags=["apps"])


@router.post("", response_model=AppRead, status_code=status.HTTP_201_CREATED)
async def create(
    payload: AppCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AppRead:
    app = await create_app(session, current_user=current_user, payload=payload)
    return AppRead.model_validate(app)


@router.get("", response_model=list[AppRead])
async def index(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AppRead]:
    apps = await list_apps(session, current_user=current_user)
    return [AppRead.model_validate(app) for app in apps]


@router.get("/{app_id}", response_model=AppRead)
async def show(
    app_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AppRead:
    app = await get_app_for_user(session, app_id=app_id, current_user=current_user)
    return AppRead.model_validate(app)


@router.get("/{app_id}/status", response_model=AppServiceStatusRead)
async def service_status(
    app_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    ssh_service: Annotated[SSHService, Depends(get_ssh_service)],
) -> AppServiceStatusRead:
    app = await get_app_for_user(session, app_id=app_id, current_user=current_user)
    status_text = await check_app_service_status(app=app, settings=settings, ssh_service=ssh_service)
    return AppServiceStatusRead(service_name=app.service_name, status=status_text)


@router.post("/{app_id}/restart", response_model=AppServiceRestartRead)
async def restart_service(
    app_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    ssh_service: Annotated[SSHService, Depends(get_ssh_service)],
) -> AppServiceRestartRead:
    app = await get_app_for_user(session, app_id=app_id, current_user=current_user)
    result = await restart_app_service(
        session,
        app=app,
        current_user=current_user,
        settings=settings,
        ssh_service=ssh_service,
    )
    success = result.exit_code == 0
    message = result.stdout.strip() or result.stderr.strip() or ("Service restarted" if success else "Service restart failed")
    return AppServiceRestartRead(
        service_name=app.service_name,
        success=success,
        exit_code=result.exit_code,
        message=message,
    )


@router.get("/{app_id}/logs", response_model=AppServiceLogsRead)
async def service_logs(
    app_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    ssh_service: Annotated[SSHService, Depends(get_ssh_service)],
) -> AppServiceLogsRead:
    app = await get_app_for_user(session, app_id=app_id, current_user=current_user)
    logs = await get_app_service_logs(app=app, settings=settings, ssh_service=ssh_service)
    return AppServiceLogsRead(service_name=app.service_name, logs=logs)


@router.patch("/{app_id}", response_model=AppRead)
async def patch(
    app_id: uuid.UUID,
    payload: AppUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AppRead:
    app = await get_app_for_user(session, app_id=app_id, current_user=current_user)
    updated_app = await update_app(session, app=app, current_user=current_user, payload=payload)
    return AppRead.model_validate(updated_app)


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def destroy(
    app_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    app = await get_app_for_user(session, app_id=app_id, current_user=current_user)
    await delete_app(session, app=app)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
