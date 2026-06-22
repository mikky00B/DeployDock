import asyncio
import json
import uuid
from collections.abc import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Deployment, DeploymentLog
from app.models.deployment import DeploymentStatus

TERMINAL_DEPLOYMENT_STATUSES = {
    DeploymentStatus.success,
    DeploymentStatus.failed,
    DeploymentStatus.canceled,
}


async def stream_deployment_events(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    deployment_id: uuid.UUID,
    owner_id: uuid.UUID,
    poll_interval_seconds: float = 1.0,
) -> AsyncGenerator[str, None]:
    last_sequence = 0

    while True:
        async with sessionmaker() as session:
            logs = await _get_new_logs(
                session,
                deployment_id=deployment_id,
                last_sequence=last_sequence,
            )
            deployment = await _get_owned_deployment(
                session,
                deployment_id=deployment_id,
                owner_id=owner_id,
            )

        for log in logs:
            last_sequence = log.sequence
            yield format_sse(
                "log",
                {
                    "stream": log.stream.value,
                    "line": log.line,
                    "sequence": log.sequence,
                },
            )

        if deployment is None:
            yield format_sse("status", {"status": "not_found"})
            return

        if deployment.status in TERMINAL_DEPLOYMENT_STATUSES:
            yield format_sse("status", {"status": deployment.status.value})
            return

        if not logs:
            yield format_sse("heartbeat", {"status": deployment.status.value})

        await asyncio.sleep(poll_interval_seconds)


def format_sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


async def _get_new_logs(
    session: AsyncSession,
    *,
    deployment_id: uuid.UUID,
    last_sequence: int,
) -> list[DeploymentLog]:
    result = await session.execute(
        select(DeploymentLog)
        .where(
            DeploymentLog.deployment_id == deployment_id,
            DeploymentLog.sequence > last_sequence,
        )
        .order_by(DeploymentLog.sequence.asc())
    )
    return list(result.scalars().all())


async def _get_owned_deployment(
    session: AsyncSession,
    *,
    deployment_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> Deployment | None:
    result = await session.execute(
        select(Deployment).where(
            Deployment.id == deployment_id,
            Deployment.owner_id == owner_id,
        )
    )
    return result.scalar_one_or_none()
