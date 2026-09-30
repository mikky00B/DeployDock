"""The SSE stream is notification-driven, with polling as a backstop."""

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import App, Deployment, DeploymentLog, Server, User
from app.models.deployment import DeploymentKind, DeploymentStatus
from app.models.deployment_log import DeploymentLogStream
from app.services.deployment_events import DeploymentEventBus, deployment_event_bus
from app.services.deployment_stream_service import format_sse, stream_deployment_events


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def seed_deployment(session, status=DeploymentStatus.running) -> Deployment:
    user = User(email="owner@example.com", hashed_password="x")
    session.add(user)
    await session.flush()
    server = Server(
        owner_id=user.id,
        name="VPS",
        host="203.0.113.10",
        port=22,
        username="deploy",
        encrypted_private_key="encrypted",
    )
    session.add(server)
    await session.flush()
    app_record = App(
        owner_id=user.id,
        server_id=server.id,
        name="Watchdog",
        repository_url="https://example.com/repo.git",
        app_path="/opt/watchdog",
        deploy_command="git pull",
    )
    session.add(app_record)
    await session.flush()
    deployment = Deployment(
        owner_id=user.id,
        app_id=app_record.id,
        server_id=server.id,
        status=status,
        kind=DeploymentKind.deploy,
    )
    session.add(deployment)
    await session.flush()
    await session.commit()
    return deployment


def add_log(session, deployment, line: str, sequence: int) -> None:
    session.add(
        DeploymentLog(
            deployment_id=deployment.id,
            stream=DeploymentLogStream.stdout,
            line=line,
            sequence=sequence,
        )
    )


def test_format_sse_shape() -> None:
    assert format_sse("log", {"line": "hi"}) == 'event: log\ndata: {"line":"hi"}\n\n'


async def test_stream_replays_existing_logs_then_terminates(session_factory) -> None:
    async with session_factory() as session:
        deployment = await seed_deployment(session, status=DeploymentStatus.success)
        add_log(session, deployment, "pulling", 1)
        add_log(session, deployment, "restarted", 2)
        await session.commit()

    events = [
        event
        async for event in stream_deployment_events(
            sessionmaker=session_factory,
            deployment_id=deployment.id,
            owner_id=deployment.owner_id,
        )
    ]

    assert "pulling" in events[0]
    assert "restarted" in events[1]
    assert '"status":"success"' in events[-1]


async def test_stream_terminates_on_rolled_back_status(session_factory) -> None:
    """rolled_back is terminal: it ends the stream instead of polling forever."""
    async with session_factory() as session:
        deployment = await seed_deployment(session, status=DeploymentStatus.rolled_back)
        add_log(session, deployment, "rolled back", 1)
        await session.commit()

    events = [
        event
        async for event in stream_deployment_events(
            sessionmaker=session_factory,
            deployment_id=deployment.id,
            owner_id=deployment.owner_id,
        )
    ]

    assert '"status":"rolled_back"' in events[-1]


async def test_stream_terminates_for_rolled_back_deployments(session_factory) -> None:
    """rolled_back became a terminal status with the Phase 3 state machine."""
    async with session_factory() as session:
        deployment = await seed_deployment(session, status=DeploymentStatus.rolled_back)

    events = [
        event
        async for event in stream_deployment_events(
            sessionmaker=session_factory,
            deployment_id=deployment.id,
            owner_id=deployment.owner_id,
        )
    ]

    assert events == [format_sse("status", {"status": "rolled_back"})]


async def test_stream_terminates_for_canceled_deployments(session_factory) -> None:
    async with session_factory() as session:
        deployment = await seed_deployment(session, status=DeploymentStatus.canceled)
        add_log(session, deployment, "canceling", 1)
        await session.commit()

    events = [
        event
        async for event in stream_deployment_events(
            sessionmaker=session_factory,
            deployment_id=deployment.id,
            owner_id=deployment.owner_id,
        )
    ]

    assert "canceling" in events[0]
    assert '"status":"canceled"' in events[-1]


async def test_stream_reports_not_found_for_another_owner(session_factory) -> None:
    async with session_factory() as session:
        deployment = await seed_deployment(session)

    events = [
        event
        async for event in stream_deployment_events(
            sessionmaker=session_factory,
            deployment_id=deployment.id,
            owner_id=uuid.uuid4(),
        )
    ]

    assert events == [format_sse("status", {"status": "not_found"})]


async def test_stream_emits_a_heartbeat_when_idle(session_factory) -> None:
    async with session_factory() as session:
        deployment = await seed_deployment(session)

    generator = stream_deployment_events(
        sessionmaker=session_factory,
        deployment_id=deployment.id,
        owner_id=deployment.owner_id,
        idle_poll_seconds=0.01,
    )
    first = await anext(generator)
    await generator.aclose()

    assert '"heartbeat"' in first or "heartbeat" in first


async def test_stream_wakes_immediately_on_a_notification(session_factory) -> None:
    async with session_factory() as session:
        deployment = await seed_deployment(session)

    generator = stream_deployment_events(
        sessionmaker=session_factory,
        deployment_id=deployment.id,
        owner_id=deployment.owner_id,
        idle_poll_seconds=30.0,  # long enough that only a notification can wake it
    )

    async def write_log_then_notify() -> None:
        await asyncio.sleep(0.05)
        async with session_factory() as session:
            add_log(session, deployment, "late line", 1)
            deployment_row = await session.get(Deployment, deployment.id)
            deployment_row.status = DeploymentStatus.success
            await session.commit()
        deployment_event_bus.notify(deployment.id)

    writer = asyncio.create_task(write_log_then_notify())
    try:
        # Without the notification this would block for idle_poll_seconds.
        event = await asyncio.wait_for(anext(generator), timeout=5)
    finally:
        await writer
        await generator.aclose()

    assert "late line" in event


async def test_event_bus_wait_times_out_without_a_notification() -> None:
    bus = DeploymentEventBus()

    assert await bus.wait(uuid.uuid4(), timeout=0.01) is False


async def test_event_bus_wait_returns_true_when_notified() -> None:
    bus = DeploymentEventBus()
    deployment_id = uuid.uuid4()

    async def notify_soon() -> None:
        await asyncio.sleep(0.01)
        bus.notify(deployment_id)

    task = asyncio.create_task(notify_soon())
    result = await bus.wait(deployment_id, timeout=5)
    await task

    assert result is True


async def test_event_bus_cleans_up_its_waiters() -> None:
    bus = DeploymentEventBus()
    deployment_id = uuid.uuid4()

    await bus.wait(deployment_id, timeout=0.01)

    assert deployment_id not in bus._waiters
