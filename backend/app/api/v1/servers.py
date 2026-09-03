import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models import User
from app.schemas.server import (
    ServerConnectionTestRead,
    ServerCreate,
    ServerHostKeyRead,
    ServerRead,
    ServerUpdate,
)
from app.services.server_service import (
    create_server,
    delete_server,
    get_server_for_user,
    list_servers,
    repin_server_host_key,
    test_server_connection,
    update_server,
)
from app.services.ssh_service import SSHService, get_ssh_service

router = APIRouter(prefix="/servers", tags=["servers"])


@router.post("", response_model=ServerRead, status_code=status.HTTP_201_CREATED)
async def create(
    payload: ServerCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ServerRead:
    server = await create_server(
        session,
        current_user=current_user,
        payload=payload,
        settings=settings,
    )
    return ServerRead.model_validate(server)


@router.get("", response_model=list[ServerRead])
async def index(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ServerRead]:
    servers = await list_servers(session, current_user=current_user)
    return [ServerRead.model_validate(server) for server in servers]


@router.get("/{server_id}", response_model=ServerRead)
async def show(
    server_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ServerRead:
    server = await get_server_for_user(session, server_id=server_id, current_user=current_user)
    return ServerRead.model_validate(server)


@router.patch("/{server_id}", response_model=ServerRead)
async def patch(
    server_id: uuid.UUID,
    payload: ServerUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ServerRead:
    server = await get_server_for_user(session, server_id=server_id, current_user=current_user)
    updated_server = await update_server(session, server=server, payload=payload, settings=settings)
    return ServerRead.model_validate(updated_server)


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def destroy(
    server_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    server = await get_server_for_user(session, server_id=server_id, current_user=current_user)
    await delete_server(session, server=server)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{server_id}/test-connection", response_model=ServerConnectionTestRead)
async def test_connection(
    server_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    ssh_service: Annotated[SSHService, Depends(get_ssh_service)],
) -> ServerConnectionTestRead:
    server = await get_server_for_user(session, server_id=server_id, current_user=current_user)
    success, message = await test_server_connection(
        session,
        server=server,
        current_user=current_user,
        settings=settings,
        ssh_service=ssh_service,
    )
    return ServerConnectionTestRead(
        success=success,
        status=server.status,
        message=message,
        host_key_fingerprint=server.known_host_key_fingerprint,
    )


@router.post("/{server_id}/host-key", response_model=ServerHostKeyRead)
async def repin_host_key(
    server_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    ssh_service: Annotated[SSHService, Depends(get_ssh_service)],
) -> ServerHostKeyRead:
    """Re-pin the server's SSH host key after a legitimate rebuild or key rotation.

    Deliberately explicit: DeployDock never re-pins automatically, because an
    unexpected host key change is indistinguishable from an interception attempt.
    """
    server = await get_server_for_user(session, server_id=server_id, current_user=current_user)
    try:
        host_key, previous_fingerprint = await repin_server_host_key(
            session,
            server=server,
            current_user=current_user,
            ssh_service=ssh_service,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not read host key from {server.host}:{server.port}: {exc}",
        ) from exc

    return ServerHostKeyRead(
        fingerprint=host_key.fingerprint,
        algorithm=host_key.algorithm,
        previous_fingerprint=previous_fingerprint,
        message="Host key pinned. Verify this fingerprint against the server itself.",
    )
