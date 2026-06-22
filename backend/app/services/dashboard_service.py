from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import App, Deployment, Server, User
from app.models.deployment import DeploymentStatus
from app.models.server import ServerStatus
from app.schemas.audit_log import AuditLogRead
from app.schemas.dashboard import (
    DashboardAppRead,
    DashboardDeploymentRead,
    DashboardRead,
    DashboardServerRead,
    DashboardSummaryRead,
)
from app.services.audit_service import list_recent_audit_logs


async def get_dashboard(session: AsyncSession, *, current_user: User) -> DashboardRead:
    total_servers = await count_rows(session, Server, Server.owner_id == current_user.id)
    connected_servers = await count_rows(
        session,
        Server,
        Server.owner_id == current_user.id,
        Server.status == ServerStatus.connected,
    )
    total_apps = await count_rows(session, App, App.owner_id == current_user.id)
    deployed_apps = await count_rows(
        session,
        App,
        App.owner_id == current_user.id,
        App.last_successful_commit.is_not(None),
    )
    recent_failures = await count_rows(
        session,
        Deployment,
        Deployment.owner_id == current_user.id,
        Deployment.status == DeploymentStatus.failed,
        Deployment.created_at >= datetime.now(UTC) - timedelta(days=7),
    )

    recent_servers = await select_recent(session, Server, current_user=current_user, limit=4)
    recent_apps = await select_recent(session, App, current_user=current_user, limit=4)
    recent_deployments = await select_recent(session, Deployment, current_user=current_user, limit=8)
    recent_audit_logs = await list_recent_audit_logs(session, current_user=current_user, limit=8)
    latest_deployment = recent_deployments[0] if recent_deployments else None

    return DashboardRead(
        summary=DashboardSummaryRead(
            total_servers=total_servers,
            connected_servers=connected_servers,
            total_apps=total_apps,
            deployed_apps=deployed_apps,
            recent_failures=recent_failures,
            latest_deployment_status=latest_deployment.status if latest_deployment else None,
        ),
        recent_servers=[DashboardServerRead.model_validate(server) for server in recent_servers],
        recent_apps=[DashboardAppRead.model_validate(app) for app in recent_apps],
        recent_deployments=[
            DashboardDeploymentRead.model_validate(deployment)
            for deployment in recent_deployments
        ],
        recent_audit_logs=[AuditLogRead.model_validate(audit_log) for audit_log in recent_audit_logs],
    )


async def count_rows(session: AsyncSession, model, *conditions) -> int:
    result = await session.execute(select(func.count()).select_from(model).where(*conditions))
    return int(result.scalar_one())


async def select_recent(session: AsyncSession, model, *, current_user: User, limit: int):
    result = await session.execute(
        select(model)
        .where(model.owner_id == current_user.id)
        .order_by(model.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
