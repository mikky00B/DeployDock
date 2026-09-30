"""Cancellation of non-terminal deployments (spec §46, Phase 3 slice 1)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session, get_sessionmaker
from app.main import app
from app.models import AuditLog, Deployment, User
from app.models.deployment import (
    ACTIVE_DEPLOYMENT_STATUSES,
    TERMINAL_DEPLOYMENT_STATUSES,
    DeploymentKind,
    DeploymentStatus,
)
from app.services.deployment_service import cancel_deployment
from app.services.ssh_service import SSHCommandResult, get_ssh_service

TEST_PRIVATE_KEY = """-----BEGIN OPENSSH PRIVATE KEY-----
test-private-key
-----END OPENSSH PRIVATE KEY-----"""


def auth_headers(client: TestClient, email: str) -> dict[str, str]:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "strong-password",
            "full_name": "Deploy Owner",
        },
    )
    token = register_response.json()["token"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_server(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    response = client.post(
        "/api/v1/servers",
        json={
            "name": "Main VPS",
            "host": "203.0.113.10",
            "port": 22,
            "username": "deploy",
            "private_key": TEST_PRIVATE_KEY,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def create_app(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    server = create_server(client, headers)
    response = client.post(
        "/api/v1/apps",
        json={
            "name": "Watchdog",
            "server_id": server["id"],
            "repository_url": "https://github.com/example/watchdog.git",
            "branch": "main",
            "app_path": "/opt/watchdog",
            "service_name": "watchdog",
            "deploy_command": "git pull origin main\nsudo systemctl restart watchdog",
            "restart_command": "sudo systemctl restart watchdog",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


class CancelMidRunSSHService:
    """Cancels the deployment through the service layer while the deploy
    command is executing - exactly the window the runner's post-command
    checkpoint exists for."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self.session_factory = session_factory

    async def run_command(self, *, command: str, **_) -> SSHCommandResult:
        if "git rev-parse HEAD" in command:
            return SSHCommandResult(exit_code=0, stdout="abc123\n", stderr="")
        async with self.session_factory() as session:
            deployment = (await session.execute(select(Deployment))).scalar_one()
            owner = (
                await session.execute(select(User).where(User.email == "owner@example.com"))
            ).scalar_one()
            await cancel_deployment(session, deployment_id=deployment.id, current_user=owner)
        return SSHCommandResult(exit_code=0, stdout="deployed\n", stderr="")


class SuccessfulDeploymentSSHService:
    async def run_command(self, *, command: str, **_) -> SSHCommandResult:
        if "git rev-parse HEAD" in command:
            return SSHCommandResult(exit_code=0, stdout="abc123\n", stderr="")
        return SSHCommandResult(exit_code=0, stdout="deployed\n", stderr="")


@pytest.fixture
async def deployment_client(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("ENCRYPTION_KEY", "test-encryption-key")
    get_settings.cache_clear()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_get_db_session():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_sessionmaker] = lambda: async_session

    with TestClient(app) as client:
        client.async_session = async_session
        yield client

    app.dependency_overrides.clear()
    get_settings.cache_clear()
    await engine.dispose()


def seed_deployment(
    client: TestClient,
    app_record: dict[str, object],
    *,
    status: DeploymentStatus = DeploymentStatus.pending,
    kind: DeploymentKind = DeploymentKind.deploy,
) -> str:
    """Insert a deployment row directly, bypassing the API (no runner runs)."""

    async def _seed() -> str:
        async with client.async_session() as session:
            owner = (await session.execute(select(User))).scalars().first()
            deployment = Deployment(
                owner_id=owner.id,
                app_id=uuid.UUID(str(app_record["id"])),
                server_id=uuid.UUID(str(app_record["server_id"])),
                status=status,
                kind=kind,
            )
            session.add(deployment)
            await session.commit()
            return str(deployment.id)

    return client.portal.start_task_soon(_seed).result(timeout=10)


def read_audit_logs(client: TestClient, action: str) -> list[AuditLog]:
    async def _read() -> list[AuditLog]:
        async with client.async_session() as session:
            return list(
                (await session.execute(select(AuditLog).where(AuditLog.action == action))).scalars().all()
            )

    return client.portal.start_task_soon(_read).result(timeout=10)


def test_cancel_a_pending_deployment_that_was_never_started(deployment_client) -> None:
    client = deployment_client
    headers = auth_headers(client, "owner@example.com")
    app_record = create_app(client, headers)
    deployment_id = seed_deployment(client, app_record)

    response = client.post(f"/api/v1/deployments/{deployment_id}/cancel", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == DeploymentStatus.canceled.value
    assert body["finished_at"] is not None
    assert body["duration_seconds"] is None  # never started, so no duration

    async def _read_back() -> tuple[DeploymentStatus, tuple[str, str]]:
        async with client.async_session() as session:
            row = await session.get(Deployment, uuid.UUID(deployment_id))
            audit_log = (
                await session.execute(select(AuditLog).where(AuditLog.action == "deployment.canceled"))
            ).scalar_one()
            return row.status, (audit_log.entity_type, str(audit_log.entity_id))

    status_after, audit_entity = client.portal.start_task_soon(_read_back).result(timeout=10)

    assert status_after is DeploymentStatus.canceled
    assert audit_entity == ("deployment", deployment_id)


def test_cancel_is_idempotent_while_pending(deployment_client) -> None:
    client = deployment_client
    headers = auth_headers(client, "owner@example.com")
    app_record = create_app(client, headers)
    deployment_id = seed_deployment(client, app_record)

    first = client.post(f"/api/v1/deployments/{deployment_id}/cancel", headers=headers)
    second = client.post(f"/api/v1/deployments/{deployment_id}/cancel", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == DeploymentStatus.canceled.value


def test_cancel_a_pending_rollback_deployment(deployment_client) -> None:
    client = deployment_client
    headers = auth_headers(client, "owner@example.com")
    app_record = create_app(client, headers)
    deployment_id = seed_deployment(client, app_record, kind=DeploymentKind.rollback)

    response = client.post(f"/api/v1/deployments/{deployment_id}/cancel", headers=headers)

    assert response.status_code == 200
    assert response.json()["kind"] == DeploymentKind.rollback.value
    assert response.json()["status"] == DeploymentStatus.canceled.value


def test_cancel_is_rejected_for_a_terminal_deployment(deployment_client) -> None:
    client = deployment_client
    headers = auth_headers(client, "owner@example.com")
    app_record = create_app(client, headers)
    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulDeploymentSSHService()
    deployment = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers).json()

    response = client.post(f"/api/v1/deployments/{deployment['id']}/cancel", headers=headers)

    assert response.status_code == 409
    assert "already success" in response.json()["detail"]
    detail = client.get(f"/api/v1/deployments/{deployment['id']}", headers=headers).json()
    assert detail["status"] == DeploymentStatus.success.value


def test_cancel_is_owner_scoped(deployment_client) -> None:
    client = deployment_client
    owner_headers = auth_headers(client, "owner@example.com")
    other_headers = auth_headers(client, "other@example.com")
    app_record = create_app(client, owner_headers)
    deployment_id = seed_deployment(client, app_record)

    response = client.post(f"/api/v1/deployments/{deployment_id}/cancel", headers=other_headers)

    assert response.status_code == 404


def test_cancel_requires_authentication(deployment_client) -> None:
    client = deployment_client
    headers = auth_headers(client, "owner@example.com")
    app_record = create_app(client, headers)
    deployment_id = seed_deployment(client, app_record)

    response = client.post(f"/api/v1/deployments/{deployment_id}/cancel")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_runner_honours_a_cancel_that_landed_mid_run(deployment_client) -> None:
    """The SSH bridge cannot abort an executing command, so the runner checks the
    committed status after the command returns and keeps the canceled status."""
    client = deployment_client
    headers = auth_headers(client, "owner@example.com")
    app_record = create_app(client, headers)
    app.dependency_overrides[get_ssh_service] = lambda: CancelMidRunSSHService(client.async_session)

    deploy_response = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers)

    assert deploy_response.status_code == 202
    deployment_id = deploy_response.json()["id"]
    detail = client.get(f"/api/v1/deployments/{deployment_id}", headers=headers).json()

    assert detail["status"] == DeploymentStatus.canceled.value
    assert detail["exit_code"] is None
    assert detail["commit_sha"] is None  # success bookkeeping must not run
    assert detail["finished_at"] is not None

    logs_response = client.get(f"/api/v1/deployments/{deployment_id}/logs", headers=headers)
    log_lines = [log["line"] for log in logs_response.json()]
    assert "Deployment canceled; ignoring the result of the command that was already running" in log_lines

    audit_logs = read_audit_logs(client, "deployment.canceled")
    assert len(audit_logs) == 2  # one from the API path, one from the runner checkpoint
    assert all(audit_log.entity_type == "deployment" for audit_log in audit_logs)


def test_status_groups_partition_the_enum() -> None:
    """The concurrency guard, the SSE stream, and the orphan sweep must cover
    every status exactly once - new pipeline states have to pick a side."""
    assert not set(ACTIVE_DEPLOYMENT_STATUSES) & set(TERMINAL_DEPLOYMENT_STATUSES)
    assert set(ACTIVE_DEPLOYMENT_STATUSES) | set(TERMINAL_DEPLOYMENT_STATUSES) == set(DeploymentStatus)


def test_a_pipeline_status_blocks_a_new_deploy(deployment_client) -> None:
    """Every non-terminal status must keep the one-active-deployment guard up."""
    client = deployment_client
    headers = auth_headers(client, "owner@example.com")
    app_record = create_app(client, headers)
    seed_deployment(client, app_record, status=DeploymentStatus.building)

    response = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers)

    assert response.status_code == 409
    assert "already building" in response.json()["detail"]


def test_a_canceled_deployment_does_not_block_a_new_deploy(deployment_client) -> None:
    client = deployment_client
    headers = auth_headers(client, "owner@example.com")
    app_record = create_app(client, headers)
    seed_deployment(client, app_record, status=DeploymentStatus.canceled)
    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulDeploymentSSHService()

    response = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers)

    assert response.status_code == 202

