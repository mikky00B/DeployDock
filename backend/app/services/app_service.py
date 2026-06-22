import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.encryption import decrypt_text
from app.models import App, User
from app.schemas.app import AppCreate, AppUpdate
from app.services.audit_service import create_audit_log
from app.services.server_service import get_server_for_user
from app.services.ssh_service import SSHCommandResult, SSHService


async def create_app(
    session: AsyncSession,
    *,
    current_user: User,
    payload: AppCreate,
) -> App:
    await get_server_for_user(session, server_id=payload.server_id, current_user=current_user)

    app = App(
        owner_id=current_user.id,
        server_id=payload.server_id,
        name=payload.name,
        repository_url=payload.repository_url,
        branch=payload.branch,
        app_path=payload.app_path,
        service_name=payload.service_name,
        deploy_command=payload.deploy_command,
        restart_command=payload.restart_command,
        healthcheck_url=payload.healthcheck_url,
    )
    session.add(app)
    await session.flush()
    await create_audit_log(
        session,
        current_user=current_user,
        action="app.created",
        entity_type="app",
        entity_id=app.id,
        metadata={"name": app.name, "server_id": str(app.server_id)},
    )
    await session.commit()
    await session.refresh(app)
    return app


async def list_apps(session: AsyncSession, *, current_user: User) -> list[App]:
    result = await session.execute(
        select(App)
        .where(App.owner_id == current_user.id)
        .order_by(App.created_at.desc())
    )
    return list(result.scalars().all())


async def get_app_for_user(
    session: AsyncSession,
    *,
    app_id: uuid.UUID,
    current_user: User,
) -> App:
    result = await session.execute(
        select(App)
        .options(selectinload(App.server))
        .where(App.id == app_id, App.owner_id == current_user.id)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    return app


async def update_app(
    session: AsyncSession,
    *,
    app: App,
    current_user: User,
    payload: AppUpdate,
) -> App:
    update_data = payload.model_dump(exclude_unset=True)

    if "server_id" in update_data:
        await get_server_for_user(session, server_id=update_data["server_id"], current_user=current_user)

    for field_name, value in update_data.items():
        setattr(app, field_name, value)

    if update_data:
        await create_audit_log(
            session,
            current_user=current_user,
            action="app.updated",
            entity_type="app",
            entity_id=app.id,
            metadata={"updated_fields": sorted(update_data.keys())},
        )
    await session.commit()
    await session.refresh(app)
    return app


async def delete_app(session: AsyncSession, *, app: App) -> None:
    await session.delete(app)
    await session.commit()


async def check_app_service_status(
    *,
    app: App,
    settings: Settings,
    ssh_service: SSHService,
) -> str:
    if not app.service_name:
        return "unknown"

    result = await run_app_command(
        app=app,
        settings=settings,
        ssh_service=ssh_service,
        command=f"systemctl is-active {quote_shell_word(app.service_name)}",
        timeout_seconds=15,
    )
    status_text = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    return status_text or "unknown"


async def restart_app_service(
    session: AsyncSession,
    *,
    app: App,
    current_user: User,
    settings: Settings,
    ssh_service: SSHService,
) -> SSHCommandResult:
    command = app.restart_command
    if command is None and app.service_name:
        command = f"sudo systemctl restart {quote_shell_word(app.service_name)}"
    if command is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="App does not have a restart command or service name",
        )

    result = await run_app_command(
        app=app,
        settings=settings,
        ssh_service=ssh_service,
        command=command,
        timeout_seconds=60,
    )
    await create_audit_log(
        session,
        current_user=current_user,
        action="service.restarted",
        entity_type="app",
        entity_id=app.id,
        metadata={
            "service_name": app.service_name,
            "exit_code": result.exit_code,
            "success": result.exit_code == 0,
        },
    )
    await session.commit()
    return result


async def get_app_service_logs(
    *,
    app: App,
    settings: Settings,
    ssh_service: SSHService,
) -> str:
    if not app.service_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="App does not have a service name")

    result = await run_app_command(
        app=app,
        settings=settings,
        ssh_service=ssh_service,
        command=f"journalctl -u {quote_shell_word(app.service_name)} -n 100 --no-pager",
        timeout_seconds=30,
    )
    if result.exit_code != 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.stderr.strip() or "Could not read service logs",
        )
    return result.stdout


async def run_app_command(
    *,
    app: App,
    settings: Settings,
    ssh_service: SSHService,
    command: str,
    timeout_seconds: int,
) -> SSHCommandResult:
    private_key = decrypt_text(app.server.encrypted_private_key, settings.encryption_key)
    try:
        return await ssh_service.run_command(
            host=app.server.host,
            port=app.server.port,
            username=app.server.username,
            private_key=private_key,
            command=command,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SSH command failed: {exc}",
        ) from exc


def quote_shell_word(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
