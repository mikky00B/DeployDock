import json
import uuid
from collections.abc import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Deployment, DeploymentLog
from app.models.deployment import TERMINAL_DEPLOYMENT_STATUSES as _TERMINAL_STATUSES
from app.models.deployment import DeploymentStatus
from app.services.deployment_events import deployment_event_bus

TERMINAL_DEPLOYMENT_STATUSES: frozenset[DeploymentStatus] = frozenset(_TERMINAL_STATUSES)

# How long a stream waits for a notification before checking the database anyway.
# Also the heartbeat interval, which keeps proxies from closing an idle connection.
IDLE_POLL_SECONDS = 15.0


async def stream_deployment_events(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    deployment_id: uuid.UUID,
    owner_id: uuid.UUID,
    idle_poll_seconds: float = IDLE_POLL_SECONDS,
    after_sequence: int = 0,
) -> AsyncGenerator[str, None]:
    """The deployment log stream as SSE frames.

    ``after_sequence`` is the resume cursor (audit H5): the Last-Event-ID a
    reconnecting client saw last, so a dropped connection resumes instead of
    re-downloading the whole log. Every log frame carries ``id: <sequence>``
    to feed that contract, and ``retry`` tells clients how fast to reconnect.
    """
    last_sequence = after_sequence

    # Reconnection speed for any EventSource-style client (audit H5), sent
    # once up front per the SSE retry contract.
    yield "retry: 2000\n\n"

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
                event_id=str(log.sequence),
            )

        if deployment is None:
            yield format_sse("status", {"status": "not_found"})
            return

        if deployment.status in TERMINAL_DEPLOYMENT_STATUSES:
            yield format_sse("status", {"status": deployment.status.value})
            return

        if logs:
            # More output may already be queued; loop immediately rather than sleeping.
            continue

        # Sleep until the runner signals new output, or the idle timeout expires.
        woken = await deployment_event_bus.wait(deployment_id, timeout=idle_poll_seconds)
        if not woken:
            yield format_sse("heartbeat", {"status": deployment.status.value})


def format_sse(event: str, data: dict[str, object], event_id: str | None = None) -> str:
    id_line = f"id: {event_id}\n" if event_id is not None else ""
    return f"{id_line}event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


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
