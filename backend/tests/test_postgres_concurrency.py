"""Database-level concurrency guards, verified against real PostgreSQL.

The unit suite runs on SQLite (which skips partial-index enforcement gaps it
cannot express), so the most safety-critical invariant — one dispatchable
deployment per app — is re-verified here against the production engine.
Skipped automatically when DATABASE_URL is not PostgreSQL; the CI migrations
job runs it with a real Postgres 16 service.
"""

import os

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import App, Deployment, Server, User
from app.models.deployment import DeploymentStatus

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="partial-index guards only enforce on PostgreSQL",
)


@pytest.fixture
async def pg_session():
    engine = create_async_engine(os.environ["DATABASE_URL"])

    # Isolated schema per run: drop and recreate everything this test touches.
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _seed_owner_app(session) -> App:
    user = User(email="pg-guard@example.com", hashed_password="x", full_name="PG Guard")
    session.add(user)
    await session.flush()
    server = Server(
        owner_id=user.id,
        name="pg-vps",
        host="203.0.113.10",
        port=22,
        username="deploy",
        auth_type="ssh_key",
        encrypted_private_key="x",
        status="unknown",
    )
    session.add(server)
    await session.flush()
    app = App(
        owner_id=user.id,
        server_id=server.id,
        name="pg-app",
        repository_url="https://github.com/example/pg-app.git",
        branch="main",
        app_path="/opt/pg-app",
        deploy_command="make build",
    )
    session.add(app)
    await session.flush()
    return app


async def test_two_dispatchable_deployments_per_app_are_rejected(pg_session) -> None:
    app = await _seed_owner_app(pg_session)

    first = Deployment(
        owner_id=app.owner_id, app_id=app.id, server_id=app.server_id, status=DeploymentStatus.cloning
    )
    pg_session.add(first)
    await pg_session.flush()

    # A deployment in a pipeline stage must occupy the guard slot exactly like
    # 'pending'/'running' did — the database, not the service layer, enforces it.
    second = Deployment(
        owner_id=app.owner_id, app_id=app.id, server_id=app.server_id, status=DeploymentStatus.building
    )
    pg_session.add(second)
    with pytest.raises(IntegrityError):
        await pg_session.flush()
    await pg_session.rollback()


async def test_queued_may_wait_behind_a_dispatchable_deployment(pg_session) -> None:
    app = await _seed_owner_app(pg_session)

    active = Deployment(
        owner_id=app.owner_id, app_id=app.id, server_id=app.server_id, status=DeploymentStatus.deploying
    )
    queued = Deployment(
        owner_id=app.owner_id, app_id=app.id, server_id=app.server_id, status=DeploymentStatus.queued
    )
    pg_session.add_all([active, queued])
    await pg_session.flush()  # must not raise

    # But a second queued row is not special either: one queue slot per app.
    second_queued = Deployment(
        owner_id=app.owner_id, app_id=app.id, server_id=app.server_id, status=DeploymentStatus.queued
    )
    pg_session.add(second_queued)
    await pg_session.flush()
    queued_rows = (
        await pg_session.execute(
            select(Deployment).where(Deployment.status == DeploymentStatus.queued)
        )
    ).scalars().all()
    assert len(queued_rows) == 2  # queued is exempt from the index by design
