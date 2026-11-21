"""Data retention for unbounded tables (audit M11).

Deployment logs and webhook deliveries grow forever without a lifecycle
policy; the VPS disk eventually fills and takes Postgres down with it. The
periodic sweep prunes both: log rows belonging to terminal deployments older
than the retention window, and webhook deliveries past theirs.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Deployment, DeploymentLog, DeploymentStatus, WebhookDelivery

logger = logging.getLogger("deploydock.retention")

TERMINAL_STATUSES = (
    DeploymentStatus.success,
    DeploymentStatus.failed,
    DeploymentStatus.canceled,
    DeploymentStatus.rolled_back,
    DeploymentStatus.superseded,
)


async def prune_expired_data(
    session: AsyncSession,
    *,
    log_retention_days: int,
    delivery_retention_days: int,
) -> tuple[int, int]:
    """Delete expired log and delivery rows. Returns (logs, deliveries) pruned."""
    now = datetime.now(UTC)

    log_cutoff = now - timedelta(days=log_retention_days)
    terminal_ids = select(Deployment.id).where(
        Deployment.status.in_(TERMINAL_STATUSES),
        Deployment.finished_at.is_not(None),
        Deployment.finished_at <= log_cutoff,
    )
    logs_result = await session.execute(
        delete(DeploymentLog)
        .where(DeploymentLog.deployment_id.in_(terminal_ids))
        .returning(DeploymentLog.id)
    )
    pruned_logs = len(logs_result.scalars().all())

    delivery_cutoff = now - timedelta(days=delivery_retention_days)
    delivery_result = await session.execute(
        delete(WebhookDelivery).where(WebhookDelivery.created_at <= delivery_cutoff)
    )
    pruned_deliveries = delivery_result.rowcount or 0

    await session.commit()
    if pruned_logs or pruned_deliveries:
        logger.info(
            "Retention pruned %s deployment log row(s) and %s webhook delivery row(s)",
            pruned_logs,
            pruned_deliveries,
        )
    return pruned_logs, pruned_deliveries
