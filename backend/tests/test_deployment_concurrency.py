"""Guards around at-most-one-active-deployment-per-app, and orphan recovery."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import App, Deployment, Server, User
from app.models.deployment import DeploymentKind, DeploymentStatus
from app.services.deployment_service import (
    fail_orphaned_deployments,
    get_active_deployment,
)


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def seed_app(session) -> App:
    user = User(email="owner@example.com", hashed_password="x", full_name="Owner")
    session.add(user)
    await session.flush()

    server = Server(
        owner_id=user.id,
        name="Main VPS",
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
        repository_url="https://github.com/example/watchdog.git",
        app_path="/opt/watchdog",
        deploy_command="git pull",
    )
    session.add(app_record)
    await session.flush()
    return app_record


def make_deployment(app_record: App, status: DeploymentStatus, **overrides) -> Deployment:
    return Deployment(
        owner_id=app_record.owner_id,
        app_id=app_record.id,
        server_id=app_record.server_id,
        status=status,
        kind=DeploymentKind.deploy,
        **overrides,
    )


async def test_database_rejects_a_second_active_deployment(session_factory) -> None:
    async with session_factory() as session:
        app_record = await seed_app(session)
        session.add(make_deployment(app_record, DeploymentStatus.running))
        await session.commit()

        session.add(make_deployment(app_record, DeploymentStatus.pending))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_a_new_deployment_is_allowed_once_the_previous_one_is_terminal(session_factory) -> None:
    async with session_factory() as session:
        app_record = await seed_app(session)
        first = make_deployment(app_record, DeploymentStatus.running)
        session.add(first)
        await session.commit()

        first.status = DeploymentStatus.success
        await session.commit()

        session.add(make_deployment(app_record, DeploymentStatus.pending))
        await session.commit()  # must not raise

        assert len((await session.execute(select(Deployment))).scalars().all()) == 2


async def test_two_apps_may_deploy_at_the_same_time(session_factory) -> None:
    async with session_factory() as session:
        first_app = await seed_app(session)
        second_app = App(
            owner_id=first_app.owner_id,
            server_id=first_app.server_id,
            name="Gatekeeper",
            repository_url="https://github.com/example/gatekeeper.git",
            app_path="/opt/gatekeeper",
            deploy_command="git pull",
        )
        session.add(second_app)
        await session.flush()

        session.add(make_deployment(first_app, DeploymentStatus.running))
        session.add(make_deployment(second_app, DeploymentStatus.running))
        await session.commit()  # must not raise


@pytest.mark.parametrize(
    "status",
    [
        DeploymentStatus.pending,
        DeploymentStatus.running,
        DeploymentStatus.queued,
        DeploymentStatus.building,
        DeploymentStatus.health_check,
    ],
)
async def test_get_active_deployment_finds_non_terminal_rows(session_factory, status) -> None:
    async with session_factory() as session:
        app_record = await seed_app(session)
        session.add(make_deployment(app_record, status))
        await session.commit()

        active = await get_active_deployment(session, app_id=app_record.id)

        assert active is not None
        assert active.status is status


async def test_get_active_deployment_ignores_finished_rows(session_factory) -> None:
    async with session_factory() as session:
        app_record = await seed_app(session)
        session.add(make_deployment(app_record, DeploymentStatus.success))
        await session.commit()

        assert await get_active_deployment(session, app_id=app_record.id) is None


async def test_get_active_deployment_is_scoped_to_the_app(session_factory) -> None:
    async with session_factory() as session:
        app_record = await seed_app(session)
        session.add(make_deployment(app_record, DeploymentStatus.running))
        await session.commit()

        assert await get_active_deployment(session, app_id=uuid.uuid4()) is None


async def test_orphan_sweep_fails_stale_deployments_and_records_duration(session_factory) -> None:
    async with session_factory() as session:
        app_record = await seed_app(session)
        started = datetime.now(UTC) - timedelta(hours=3)
        stale = make_deployment(app_record, DeploymentStatus.running, started_at=started)
        stale.created_at = started
        session.add(stale)
        await session.commit()

        reclaimed = await fail_orphaned_deployments(session, older_than_seconds=3600)
        await session.refresh(stale)

        assert reclaimed == 1
        assert stale.status is DeploymentStatus.failed
        assert "interrupted" in stale.error_message
        assert stale.finished_at is not None
        assert stale.duration_seconds is not None and stale.duration_seconds > 0


async def test_orphan_sweep_leaves_recent_deployments_alone(session_factory) -> None:
    async with session_factory() as session:
        app_record = await seed_app(session)
        fresh = make_deployment(app_record, DeploymentStatus.running, started_at=datetime.now(UTC))
        session.add(fresh)
        await session.commit()

        reclaimed = await fail_orphaned_deployments(session, older_than_seconds=3600)
        await session.refresh(fresh)

        assert reclaimed == 0
        assert fresh.status is DeploymentStatus.running


async def test_orphan_sweep_unblocks_the_next_deployment(session_factory) -> None:
    async with session_factory() as session:
        app_record = await seed_app(session)
        started = datetime.now(UTC) - timedelta(hours=3)
        stale = make_deployment(app_record, DeploymentStatus.running, started_at=started)
        stale.created_at = started
        session.add(stale)
        await session.commit()

        await fail_orphaned_deployments(session, older_than_seconds=3600)

        session.add(make_deployment(app_record, DeploymentStatus.pending))
        await session.commit()  # must not raise


async def test_creating_a_deployment_supersedes_the_queued_one(session_factory) -> None:
    """v3 §4.3: stale code must not run — a deployment created while another is
    queued marks the queued one superseded and takes the queue slot."""
    from app.services.deployment_service import create_deployment

    async with session_factory() as session:
        app_record = await seed_app(session)
        session.add(make_deployment(app_record, DeploymentStatus.success))  # for get_app_for_user owner
        session.add(make_deployment(app_record, DeploymentStatus.queued))
        await session.commit()

        user = (await session.execute(select(User))).scalar_one()
        replacement = await create_deployment(
            session, app_id=app_record.id, current_user=user
        )

        assert replacement.status is DeploymentStatus.pending  # nothing dispatchable remains
        old = (
            await session.execute(
                select(Deployment).where(Deployment.status == DeploymentStatus.superseded)
            )
        ).scalar_one()
        assert old.status is DeploymentStatus.superseded
        assert old.finished_at is not None


async def test_supersede_queues_behind_a_running_deployment(session_factory) -> None:
    """Superseding a queued row while a real deploy is running: the new one
    waits behind the runner instead of starting immediately."""
    from app.services.deployment_service import create_deployment

    async with session_factory() as session:
        app_record = await seed_app(session)
        session.add(
            make_deployment(
                app_record, DeploymentStatus.running, created_at=datetime(2026, 1, 1, tzinfo=UTC)
            )
        )
        session.add(
            make_deployment(
                app_record, DeploymentStatus.queued, created_at=datetime(2026, 1, 2, tzinfo=UTC)
            )
        )
        await session.commit()

        user = (await session.execute(select(User))).scalar_one()
        replacement = await create_deployment(
            session, app_id=app_record.id, current_user=user, queue_if_active=True
        )

        assert replacement.status is DeploymentStatus.queued
        superseded_count = len(
            (
                await session.execute(
                    select(Deployment).where(Deployment.status == DeploymentStatus.superseded)
                )
            ).scalars().all()
        )
        assert superseded_count == 1


async def test_superseded_rows_do_not_block_or_conflict(session_factory) -> None:
    """A superseded row is terminal: the guard ignores it and two superseded
    rows may coexist (a queue replaced twice in a row)."""
    from app.services.deployment_service import create_deployment

    async with session_factory() as session:
        app_record = await seed_app(session)
        user = (await session.execute(select(User))).scalar_one()

        session.add(
            make_deployment(
                app_record, DeploymentStatus.running, created_at=datetime(2026, 1, 1, tzinfo=UTC)
            )
        )
        first_queued = make_deployment(
            app_record, DeploymentStatus.queued, created_at=datetime(2026, 1, 2, tzinfo=UTC)
        )
        session.add(first_queued)
        await session.commit()

        first = await create_deployment(
            session, app_id=app_record.id, current_user=user, queue_if_active=True
        )
        assert first.status is DeploymentStatus.queued

        # A third push replaces the (now new) queued row again.
        second = await create_deployment(
            session, app_id=app_record.id, current_user=user, queue_if_active=True
        )
        assert second.status is DeploymentStatus.queued

        statuses = (
            await session.execute(select(Deployment.status).order_by(Deployment.created_at))
        ).scalars().all()
        assert statuses.count(DeploymentStatus.superseded) == 2


async def test_interactive_deploy_is_refused_without_superseding(session_factory) -> None:
    """A 409 must not mutate state: an interactive deploy facing a running
    deployment (with a queued one behind it) refuses cleanly and leaves the
    queued row untouched."""
    import pytest as _pytest
    from fastapi import HTTPException

    from app.services.deployment_service import create_deployment

    async with session_factory() as session:
        app_record = await seed_app(session)
        queued_row = make_deployment(
            app_record, DeploymentStatus.queued, created_at=datetime(2026, 1, 2, tzinfo=UTC)
        )
        session.add(
            make_deployment(
                app_record, DeploymentStatus.running, created_at=datetime(2026, 1, 1, tzinfo=UTC)
            )
        )
        session.add(queued_row)
        await session.commit()
        queued_id = queued_row.id

        user = (await session.execute(select(User))).scalar_one()
        with _pytest.raises(HTTPException) as excinfo:
            await create_deployment(session, app_id=app_record.id, current_user=user)
        assert excinfo.value.status_code == 409

        await session.rollback()
        status_after = (
            await session.execute(
                select(Deployment.status).where(Deployment.id == queued_id)
            )
        ).scalar_one()
        assert status_after is DeploymentStatus.queued
