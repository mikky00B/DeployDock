"""Registration, authentication, and liveness for DeployDock agents.

Implements the agent side of `docs/agent-protocol.md` (Phase 1 contract):

- registration tokens: single-use, short-lived, stored hashed;
- agent tokens: long-lived, shown once, stored hashed, rotatable;
- liveness: derived from `last_heartbeat_at`, never stored.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Agent, AgentRegistrationToken, AgentReportedStatus, User
from app.services.audit_service import create_audit_log

REGISTRATION_TOKEN_PREFIX = "dck_rt_"
AGENT_TOKEN_PREFIX = "dck_at_"
TOKEN_RANDOM_BYTES = 32


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(TOKEN_RANDOM_BYTES)


async def create_registration_token(
    session: AsyncSession,
    *,
    current_user: User,
    server_id: uuid.UUID | None,
    ttl_seconds: int,
) -> tuple[AgentRegistrationToken, str]:
    token = generate_token(REGISTRATION_TOKEN_PREFIX)
    record = AgentRegistrationToken(
        owner_id=current_user.id,
        server_id=server_id,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record, token


async def register_agent(
    session: AsyncSession,
    *,
    registration_token: str,
    name: str | None,
    agent_version: str | None,
    os_name: str | None,
    arch: str | None,
    settings: Settings,
) -> tuple[Agent, str]:
    """Exchange a registration token for a new agent and its agent token."""
    query = select(AgentRegistrationToken).where(
        AgentRegistrationToken.token_hash == hash_token(registration_token)
    )
    record = (await session.execute(query)).scalar_one_or_none()

    now = datetime.now(UTC)
    if record is None or record.used_at is not None or _as_utc(record.expires_at) < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Registration token is unknown, expired, or already used",
        )

    agent_token = generate_token(AGENT_TOKEN_PREFIX)
    agent = Agent(
        owner_id=record.owner_id,
        server_id=record.server_id,
        name=name or "unnamed-agent",
        token_hash=hash_token(agent_token),
        reported_status=AgentReportedStatus.active,
        agent_version=agent_version,
        os_name=os_name,
        arch=arch,
        last_heartbeat_at=now,
    )
    record.used_at = now
    session.add(agent)
    # Loaded explicitly: lazy loading relationships is not allowed on AsyncSession.
    owner = await session.get(User, record.owner_id)
    if owner is None:
        # owner_id is a non-null FK, so this only happens if the user row
        # vanished between token minting and registration.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration token owner no longer exists",
        )
    await create_audit_log(
        session,
        current_user=owner,
        action="agent.registered",
        entity_type="agent",
        entity_id=agent.id,
        metadata={"name": agent.name, "agent_version": agent_version},
    )
    await session.commit()
    await session.refresh(agent)
    return agent, agent_token


async def record_heartbeat(
    session: AsyncSession,
    *,
    agent: Agent,
    agent_version: str | None,
    metrics: dict | None,
) -> None:
    agent.last_heartbeat_at = datetime.now(UTC)
    if agent_version:
        agent.agent_version = agent_version
    if metrics is not None:
        agent.metrics = metrics
    await session.commit()


async def rotate_agent_token(
    session: AsyncSession,
    *,
    agent: Agent,
    current_user: User,
    settings: Settings,
) -> str:
    new_token = generate_token(AGENT_TOKEN_PREFIX)
    agent.token_hash = hash_token(new_token)
    await create_audit_log(
        session,
        current_user=current_user,
        action="agent.token_rotated",
        entity_type="agent",
        entity_id=agent.id,
        metadata={"name": agent.name},
    )
    await session.commit()
    return new_token


async def get_agent_for_user(
    session: AsyncSession,
    *,
    agent_id: uuid.UUID,
    current_user: User,
) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


async def get_agent_by_token(session: AsyncSession, *, token: str) -> Agent:
    """Authenticate an agent call from its bearer token.

    401 for unknown/revoked tokens; 409 for a token that is valid but whose
    agent was retired, so the agent knows to stop (and not re-register).
    """
    result = await session.execute(select(Agent).where(Agent.token_hash == hash_token(token)))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent token",
        )
    if agent.revoked_at is not None or agent.reported_status is AgentReportedStatus.retired:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent has been revoked; re-register with a fresh registration token",
        )
    return agent


async def list_agents(session: AsyncSession, *, current_user: User) -> list[Agent]:
    result = await session.execute(
        select(Agent).where(Agent.owner_id == current_user.id).order_by(Agent.created_at.desc())
    )
    return list(result.scalars().all())


def is_online(agent: Agent, settings: Settings) -> bool:
    if agent.last_heartbeat_at is None:
        return False
    age = datetime.now(UTC) - _as_utc(agent.last_heartbeat_at)
    return age <= timedelta(seconds=settings.agent_offline_after_seconds)


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
