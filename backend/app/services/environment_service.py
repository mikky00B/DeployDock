"""Environments, environment variables, and domains (spec §12, §36, §38)."""

import socket
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.secrets import decrypt_secret, encrypt_secret
from app.models import App, Domain, DomainStatus, Environment, EnvironmentVariable, Server, User
from app.schemas.environment import DomainCreate, DomainVerifyRead, EnvironmentCreate
from app.services.audit_service import create_audit_log


async def get_environment_for_user(
    session: AsyncSession,
    *,
    environment_id: uuid.UUID,
    current_user: User,
) -> Environment:
    result = await session.execute(
        select(Environment)
        .join(App, App.id == Environment.app_id)
        .where(Environment.id == environment_id, App.owner_id == current_user.id)
    )
    environment = result.scalar_one_or_none()
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    return environment


async def list_environments(session: AsyncSession, *, app: App) -> list[Environment]:
    result = await session.execute(
        select(Environment).where(Environment.app_id == app.id).order_by(Environment.created_at.asc())
    )
    return list(result.scalars().all())


async def create_environment(
    session: AsyncSession,
    *,
    app: App,
    payload: EnvironmentCreate,
    current_user: User,
) -> Environment:
    server = await session.get(Server, payload.server_id)
    if server is None or server.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    if payload.server_id != app.server_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Environment server must match the app's server for now (multi-server comes later)",
        )

    environment = Environment(
        app_id=app.id,
        server_id=payload.server_id,
        name=payload.name,
        auto_deploy=payload.auto_deploy,
        health_path=payload.health_path,
    )
    session.add(environment)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Environment '{payload.name}' already exists for this app",
        ) from exc
    await create_audit_log(
        session,
        current_user=current_user,
        action="environment.created",
        entity_type="environment",
        entity_id=environment.id,
        metadata={"app_id": str(app.id), "name": environment.name},
    )
    await session.commit()
    await session.refresh(environment)
    return environment


async def delete_environment(session: AsyncSession, *, environment: Environment) -> None:
    await session.delete(environment)
    await session.commit()


async def set_variable(
    session: AsyncSession,
    *,
    environment: Environment,
    key: str,
    value: str,
    current_user: User,
    settings: Settings,
) -> EnvironmentVariable:
    result = await session.execute(
        select(EnvironmentVariable).where(
            EnvironmentVariable.environment_id == environment.id,
            EnvironmentVariable.key == key,
        )
    )
    variable = result.scalar_one_or_none()
    encrypted = encrypt_secret(value, settings)
    if variable is None:
        variable = EnvironmentVariable(environment_id=environment.id, key=key, encrypted_value=encrypted)
        session.add(variable)
    else:
        variable.encrypted_value = encrypted
    await create_audit_log(
        session,
        current_user=current_user,
        action="environment.variable_set",
        entity_type="environment",
        entity_id=environment.id,
        metadata={"key": key},  # value deliberately excluded: secrets must not be audited
    )
    await session.commit()
    await session.refresh(variable)
    return variable


async def unset_variable(
    session: AsyncSession,
    *,
    environment: Environment,
    key: str,
    current_user: User,
) -> None:
    result = await session.execute(
        select(EnvironmentVariable).where(
            EnvironmentVariable.environment_id == environment.id,
            EnvironmentVariable.key == key,
        )
    )
    variable = result.scalar_one_or_none()
    if variable is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variable not found")
    await session.delete(variable)
    await create_audit_log(
        session,
        current_user=current_user,
        action="environment.variable_unset",
        entity_type="environment",
        entity_id=environment.id,
        metadata={"key": key},
    )
    await session.commit()


async def list_variables(
    session: AsyncSession,
    *,
    environment: Environment,
) -> list[EnvironmentVariable]:
    result = await session.execute(
        select(EnvironmentVariable)
        .where(EnvironmentVariable.environment_id == environment.id)
        .order_by(EnvironmentVariable.key.asc())
    )
    return list(result.scalars().all())


async def decrypted_variables(
    session: AsyncSession,
    *,
    environment: Environment,
    settings: Settings,
) -> dict[str, str]:
    """Variables for deployment injection — control-plane internal only."""
    variables = await list_variables(session, environment=environment)
    values: dict[str, str] = {}
    for variable in variables:
        values[variable.key] = decrypt_secret(variable.encrypted_value, settings)
    return values


async def add_domain(
    session: AsyncSession,
    *,
    environment: Environment,
    payload: DomainCreate,
    current_user: User,
) -> Domain:
    domain = Domain(environment_id=environment.id, hostname=payload.hostname)
    session.add(domain)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Domain {payload.hostname} already exists",
        ) from exc
    await create_audit_log(
        session,
        current_user=current_user,
        action="domain.added",
        entity_type="domain",
        entity_id=domain.id,
        metadata={"hostname": domain.hostname},
    )
    await session.commit()
    await session.refresh(domain)
    return domain


async def verify_domain(
    session: AsyncSession,
    *,
    domain: Domain,
    server: Server,
    current_user: User,
) -> DomainVerifyRead:
    """Verify by DNS: the hostname must resolve to the server's IP (spec §36).

    Resolves both the domain and the server host from the control plane's
    vantage point; an A-record match marks the domain verified.
    """
    expected_ips = _resolve(server.host)
    resolved_ips = _resolve(domain.hostname)
    verified = bool(expected_ips) and bool(set(expected_ips) & set(resolved_ips))

    if verified:
        domain.status = DomainStatus.verified
        domain.verified_at = domain.updated_at
        domain.last_verification_error = None
    else:
        domain.status = DomainStatus.failed
        domain.last_verification_error = (
            f"{domain.hostname} resolves to {resolved_ips or 'nothing'}; "
            f"expected {expected_ips or f'{server.host} to resolve'}"
        )
    await create_audit_log(
        session,
        current_user=current_user,
        action="domain.verified" if verified else "domain.verification_failed",
        entity_type="domain",
        entity_id=domain.id,
        metadata={"hostname": domain.hostname},
    )
    await session.commit()
    return DomainVerifyRead(
        verified=verified,
        message=(
            "DNS points at the server"
            if verified
            else (domain.last_verification_error or "DNS mismatch")
        ),
        expected_ip=sorted(expected_ips)[0] if expected_ips else None,
        resolved_ips=sorted(resolved_ips),
    )


def _resolve(host: str) -> set[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        return set()
    return {info[4][0] for info in infos}
