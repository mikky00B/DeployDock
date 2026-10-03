import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models import App, Domain, Environment, User
from app.schemas.environment import (
    DomainCreate,
    DomainRead,
    DomainVerifyRead,
    EnvironmentCreate,
    EnvironmentRead,
    VariableRead,
    VariableSet,
)
from app.services.app_service import get_app_for_user
from app.services.environment_service import (
    add_domain,
    create_environment,
    delete_environment,
    get_environment_for_user,
    list_environments,
    list_variables,
    set_variable,
    unset_variable,
    verify_domain,
)
from app.services.server_service import get_server_for_user

router = APIRouter(tags=["environments"])


async def _owned_domain(
    domain_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> Domain:
    result = await session.execute(
        select(Domain)
        .join(Environment, Environment.id == Domain.environment_id)
        .join(App, App.id == Environment.app_id)
        .where(Domain.id == domain_id, App.owner_id == current_user.id)
    )
    domain = result.scalar_one_or_none()
    if domain is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
    return domain


@router.post(
    "/apps/{app_id}/environments",
    response_model=EnvironmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_environment_endpoint(
    app_id: uuid.UUID,
    payload: EnvironmentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EnvironmentRead:
    app = await get_app_for_user(session, app_id=app_id, current_user=current_user)
    environment = await create_environment(session, app=app, payload=payload, current_user=current_user)
    return EnvironmentRead.model_validate(environment)


@router.get("/apps/{app_id}/environments", response_model=list[EnvironmentRead])
async def list_environments_endpoint(
    app_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[EnvironmentRead]:
    app = await get_app_for_user(session, app_id=app_id, current_user=current_user)
    return [EnvironmentRead.model_validate(env) for env in await list_environments(session, app=app)]


@router.get("/environments/{environment_id}", response_model=EnvironmentRead)
async def show_environment_endpoint(
    environment_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EnvironmentRead:
    environment = await get_environment_for_user(
        session, environment_id=environment_id, current_user=current_user
    )
    return EnvironmentRead.model_validate(environment)


@router.delete("/environments/{environment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_environment_endpoint(
    environment_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    environment = await get_environment_for_user(
        session, environment_id=environment_id, current_user=current_user
    )
    await delete_environment(session, environment=environment)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/environments/{environment_id}/variables", response_model=list[VariableRead])
async def list_variables_endpoint(
    environment_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[VariableRead]:
    environment = await get_environment_for_user(
        session, environment_id=environment_id, current_user=current_user
    )
    variables = await list_variables(session, environment=environment)
    # Masked reads (spec §38): presence only, never the value.
    return [VariableRead(key=variable.key, set=True) for variable in variables]


@router.put("/environments/{environment_id}/variables/{key}", response_model=VariableRead)
async def set_variable_endpoint(
    environment_id: uuid.UUID,
    key: str,
    payload: VariableSet,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> VariableRead:
    environment = await get_environment_for_user(
        session, environment_id=environment_id, current_user=current_user
    )
    if payload.key != key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Key in path and body must match")
    await set_variable(
        session,
        environment=environment,
        key=payload.key,
        value=payload.value,
        current_user=current_user,
        settings=settings,
    )
    return VariableRead(key=payload.key, set=True)


@router.delete("/environments/{environment_id}/variables/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def unset_variable_endpoint(
    environment_id: uuid.UUID,
    key: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    environment = await get_environment_for_user(
        session, environment_id=environment_id, current_user=current_user
    )
    await unset_variable(session, environment=environment, key=key, current_user=current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/environments/{environment_id}/domains",
    response_model=DomainRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_domain_endpoint(
    environment_id: uuid.UUID,
    payload: DomainCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DomainRead:
    environment = await get_environment_for_user(
        session, environment_id=environment_id, current_user=current_user
    )
    domain = await add_domain(session, environment=environment, payload=payload, current_user=current_user)
    return DomainRead.model_validate(domain)


@router.get("/environments/{environment_id}/domains", response_model=list[DomainRead])
async def list_domains_endpoint(
    environment_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[DomainRead]:
    environment = await get_environment_for_user(
        session, environment_id=environment_id, current_user=current_user
    )
    await session.refresh(environment, attribute_names=["domains"])
    return [DomainRead.model_validate(domain) for domain in environment.domains]


@router.post("/domains/{domain_id}/verify", response_model=DomainVerifyRead)
async def verify_domain_endpoint(
    domain_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DomainVerifyRead:
    domain = await _owned_domain(domain_id, current_user, session)
    environment = await get_environment_for_user(
        session, environment_id=domain.environment_id, current_user=current_user
    )
    server = await get_server_for_user(
        session, server_id=environment.server_id, current_user=current_user
    )
    return await verify_domain(session, domain=domain, server=server, current_user=current_user)
