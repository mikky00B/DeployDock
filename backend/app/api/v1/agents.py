import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models import Agent, User
from app.schemas.agent import (
    AgentCommandRead,
    AgentCommandResult,
    AgentCommandResultRead,
    AgentEventBatch,
    AgentEventBatchRead,
    AgentHeartbeat,
    AgentHeartbeatRead,
    AgentRead,
    AgentRegister,
    AgentRegisterRead,
    AgentRegistrationTokenCreate,
    AgentRegistrationTokenRead,
    AgentTokenRotateRead,
)
from app.services.agent_dispatch import claim_next_command, complete_command
from app.services.agent_event_ingestion import EventRejected, ingest_event
from app.services.agent_service import (
    create_registration_token,
    get_agent_by_token,
    get_agent_for_user,
    is_online,
    list_agents,
    record_heartbeat,
    register_agent,
    rotate_agent_token,
)

router = APIRouter(prefix="/agents", tags=["agents"])

agent_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_agent(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(agent_bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Agent:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing agent token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await get_agent_by_token(session, token=credentials.credentials)


@router.post(
    "/registration-tokens",
    response_model=AgentRegistrationTokenRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_registration_token_endpoint(
    payload: AgentRegistrationTokenCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentRegistrationTokenRead:
    record, plaintext_token = await create_registration_token(
        session,
        current_user=current_user,
        server_id=payload.server_id,
        ttl_seconds=payload.ttl_seconds,
    )
    return AgentRegistrationTokenRead(token=plaintext_token, expires_at=record.expires_at)


@router.post("/register", response_model=AgentRegisterRead, status_code=status.HTTP_201_CREATED)
async def register_agent_endpoint(
    payload: AgentRegister,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(agent_bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentRegisterRead:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing registration token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    agent, agent_token = await register_agent(
        session,
        registration_token=credentials.credentials,
        name=payload.name,
        agent_version=payload.agent_version,
        os_name=payload.os,
        arch=payload.arch,
        settings=settings,
    )
    return AgentRegisterRead(
        agent_id=agent.id,
        agent_token=agent_token,
        heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
    )


@router.get("", response_model=list[AgentRead])
async def index(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[AgentRead]:
    agents = await list_agents(session, current_user=current_user)
    return [
        AgentRead(
            id=agent.id,
            owner_id=agent.owner_id,
            server_id=agent.server_id,
            name=agent.name,
            status="online" if is_online(agent, settings) else "offline",
            agent_version=agent.agent_version,
            os=agent.os_name,
            arch=agent.arch,
            metrics=agent.metrics,
            last_heartbeat_at=agent.last_heartbeat_at,
            revoked_at=agent.revoked_at,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )
        for agent in agents
    ]


@router.post("/{agent_id}/heartbeat", response_model=AgentHeartbeatRead)
async def heartbeat(
    agent_id: uuid.UUID,
    payload: AgentHeartbeat,
    agent: Annotated[Agent, Depends(get_current_agent)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentHeartbeatRead:
    if agent.id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent token does not belong to this agent",
        )
    await record_heartbeat(
        session,
        agent=agent,
        agent_version=payload.agent_version,
        metrics=payload.metrics,
    )
    return AgentHeartbeatRead(
        status="ok",
        heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
        server_time=datetime.now(UTC),
    )


@router.post("/{agent_id}/rotate-token", response_model=AgentTokenRotateRead)
async def rotate_token(
    agent_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentTokenRotateRead:
    agent = await get_agent_for_user(session, agent_id=agent_id, current_user=current_user)
    new_token = await rotate_agent_token(session, agent=agent, current_user=current_user, settings=settings)
    return AgentTokenRotateRead(
        agent_id=agent.id,
        agent_token=new_token,
        heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
    )


@router.get("/{agent_id}/commands", response_model=list[AgentCommandRead])
async def next_commands(
    agent_id: uuid.UUID,
    agent: Annotated[Agent, Depends(get_current_agent)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AgentCommandRead]:
    """Claim the agent's oldest queued command, if any.

    Returns a one-element list (or empty): a claim is atomic per call, and one
    in-flight command per agent keeps deployments serialized on the host.
    """
    if agent.id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent token does not belong to this agent",
        )
    claimed = await claim_next_command(session, agent=agent)
    if claimed is None:
        return []
    command, claim_token = claimed
    return [
        AgentCommandRead(
            id=command.id,
            deployment_id=command.deployment_id,
            kind=command.kind.value,
            payload=command.payload,
            claim_token=claim_token,
        )
    ]


@router.post("/{agent_id}/commands/{command_id}/result", response_model=AgentCommandResultRead)
async def command_result(
    agent_id: uuid.UUID,
    command_id: uuid.UUID,
    payload: AgentCommandResult,
    agent: Annotated[Agent, Depends(get_current_agent)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentCommandResultRead:
    if agent.id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent token does not belong to this agent",
        )
    command = await complete_command(
        session,
        agent=agent,
        command_id=command_id,
        claim_token=payload.claim_token,
        succeeded=payload.succeeded,
        error_message=payload.error,
    )
    if command is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Command is not claimable by this agent (unknown id, wrong token, or already closed)",
        )
    return AgentCommandResultRead(command_id=command.id, status=command.status.value)


@router.post("/{agent_id}/events", response_model=AgentEventBatchRead)
async def agent_events(
    agent_id: uuid.UUID,
    payload: AgentEventBatch,
    agent: Annotated[Agent, Depends(get_current_agent)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentEventBatchRead:
    if agent.id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent token does not belong to this agent",
        )
    accepted = 0
    for event in payload.events:
        try:
            await ingest_event(session, agent=agent, event=event)
        except EventRejected as exc:
            # One bad event must not sink the batch; the agent's remaining
            # events stay applicable. Rejections are visible in the response.
            continue
        accepted += 1
    return AgentEventBatchRead(accepted=accepted)
