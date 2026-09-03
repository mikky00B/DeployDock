import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import (
    App,
    AuditLog,
    Deployment,
    DeploymentLog,
    DeploymentLogStream,
    DeploymentStatus,
    Server,
    ServerAuthType,
    ServerStatus,
    User,
)


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(engine, expire_on_commit=False)

    await engine.dispose()


def test_core_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "users",
        "servers",
        "apps",
        "deployments",
        "deployment_logs",
        "audit_logs",
        "agents",
        "agent_registration_tokens",
    }


def test_required_indexes_are_declared() -> None:
    indexes = {
        index.name
        for table in Base.metadata.tables.values()
        for index in table.indexes
    }

    assert "ix_users_email" in indexes
    assert "ix_servers_owner_id" in indexes
    assert "ix_apps_owner_id" in indexes
    assert "ix_deployments_app_id" in indexes
    assert "ix_deployments_status" in indexes
    assert "ix_deployment_logs_deployment_id_sequence" in indexes


async def test_core_models_can_be_created(session_factory) -> None:
    async_session = session_factory

    async with async_session() as session:
        user = User(
            email="owner@example.com",
            hashed_password="hashed-password",
            full_name="Deploy Owner",
        )
        server = Server(
            owner=user,
            name="Main VPS",
            host="203.0.113.10",
            port=22,
            username="deploy",
            auth_type=ServerAuthType.ssh_key,
            encrypted_private_key="encrypted-key",
            private_key_fingerprint="SHA256:test",
            status=ServerStatus.unknown,
        )
        app = App(
            owner=user,
            server=server,
            name="Watchdog",
            repository_url="https://example.com/watchdog.git",
            branch="main",
            app_path="/opt/watchdog",
            service_name="watchdog",
            deploy_command="git pull origin main",
        )
        deployment = Deployment(
            owner=user,
            app=app,
            server=server,
            status=DeploymentStatus.pending,
            triggered_by="manual",
        )
        deployment_log = DeploymentLog(
            deployment=deployment,
            stream=DeploymentLogStream.system,
            line="Deployment queued",
            sequence=1,
        )
        audit_log = AuditLog(
            owner=user,
            action="deployment.started",
            entity_type="deployment",
            entity_id=str(uuid.uuid4()),
            metadata_json={"source": "test"},
        )

        session.add_all([user, server, app, deployment, deployment_log, audit_log])
        await session.commit()

        user_count = await session.scalar(select(func.count()).select_from(User))
        server_count = await session.scalar(select(func.count()).select_from(Server))
        app_count = await session.scalar(select(func.count()).select_from(App))
        deployment_count = await session.scalar(select(func.count()).select_from(Deployment))
        log_count = await session.scalar(select(func.count()).select_from(DeploymentLog))
        audit_count = await session.scalar(select(func.count()).select_from(AuditLog))

    assert user_count == 1
    assert server_count == 1
    assert app_count == 1
    assert deployment_count == 1
    assert log_count == 1
    assert audit_count == 1
