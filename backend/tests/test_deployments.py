import uuid
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session, get_sessionmaker
from app.main import app
from app.models import AuditLog, Deployment, User
from app.models.deployment import DeploymentKind, DeploymentStatus
from app.services.ssh_service import SSHCommandResult, get_ssh_service

TEST_PRIVATE_KEY = """-----BEGIN OPENSSH PRIVATE KEY-----
test-private-key
-----END OPENSSH PRIVATE KEY-----"""


@dataclass
class SSHCall:
    command: str
    private_key: str


class SuccessfulDeploymentSSHService:
    def __init__(self) -> None:
        self.calls: list[SSHCall] = []

    async def run_command(
        self,
        *,
        host: str,
        port: int,
        username: str,
        private_key: str,
        command: str,
        known_host_key: str | None = None,
        timeout_seconds: int = 15,
    ) -> SSHCommandResult:
        self.calls.append(SSHCall(command=command, private_key=private_key))
        if "git rev-parse HEAD" in command and len(self.calls) == 1:
            return SSHCommandResult(exit_code=0, stdout="abc123\n", stderr="")
        if "git rev-parse HEAD" in command:
            return SSHCommandResult(exit_code=0, stdout="def456\n", stderr="")
        return SSHCommandResult(exit_code=0, stdout="pulling\nrestarted\n", stderr="")


class FailingDeploymentSSHService:
    async def run_command(self, *, command: str, **kwargs) -> SSHCommandResult:
        if "git rev-parse HEAD" in command:
            return SSHCommandResult(exit_code=0, stdout="abc123\n", stderr="")
        return SSHCommandResult(exit_code=2, stdout="pulling\n", stderr="restart failed\n")


class RollbackSSHService:
    def __init__(self) -> None:
        self.commit_outputs = ["old111\n", "aaa111\n", "aaa111\n", "bbb222\n"]
        self.calls: list[SSHCall] = []

    async def run_command(
        self,
        *,
        private_key: str,
        command: str,
        **_,
    ) -> SSHCommandResult:
        self.calls.append(SSHCall(command=command, private_key=private_key))
        if "git rev-parse HEAD" in command:
            return SSHCommandResult(exit_code=0, stdout=self.commit_outputs.pop(0), stderr="")
        if "git fetch" in command and "git checkout aaa111" in command:
            return SSHCommandResult(exit_code=0, stdout="checked out\nrestarted\n", stderr="")
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


def test_deploy_app_runs_successfully_and_saves_logs(deployment_client) -> None:
    client = deployment_client
    headers = auth_headers(client, "owner@example.com")
    app_record = create_app(client, headers)
    ssh_service = SuccessfulDeploymentSSHService()
    app.dependency_overrides[get_ssh_service] = lambda: ssh_service

    deploy_response = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers)
    deployment_id = deploy_response.json()["id"]
    detail_response = client.get(f"/api/v1/deployments/{deployment_id}", headers=headers)
    logs_response = client.get(f"/api/v1/deployments/{deployment_id}/logs", headers=headers)

    assert deploy_response.status_code == 202
    assert deploy_response.json()["status"] == DeploymentStatus.pending.value
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == DeploymentStatus.success.value
    assert detail["previous_commit_sha"] == "abc123"
    assert detail["commit_sha"] == "def456"
    assert detail["exit_code"] == 0
    assert detail["duration_seconds"] is not None
    assert [log["line"] for log in logs_response.json()] == [
        "Deployment started",
        "Previous commit: abc123",
        "pulling",
        "restarted",
        "Deployment succeeded",
    ]
    assert all(call.private_key == TEST_PRIVATE_KEY for call in ssh_service.calls)
    assert any("cd /opt/watchdog" in call.command for call in ssh_service.calls)


def test_deploy_app_marks_failed_when_command_fails(deployment_client) -> None:
    client = deployment_client
    headers = auth_headers(client, "owner@example.com")
    app_record = create_app(client, headers)
    app.dependency_overrides[get_ssh_service] = lambda: FailingDeploymentSSHService()

    deploy_response = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers)
    deployment_id = deploy_response.json()["id"]
    detail_response = client.get(f"/api/v1/deployments/{deployment_id}", headers=headers)
    logs_response = client.get(f"/api/v1/deployments/{deployment_id}/logs", headers=headers)

    assert deploy_response.status_code == 202
    detail = detail_response.json()
    assert detail["status"] == DeploymentStatus.failed.value
    assert detail["exit_code"] == 2
    assert detail["error_message"] == "restart failed"
    assert [log["stream"] for log in logs_response.json()] == ["system", "system", "stdout", "stderr", "system"]
    assert logs_response.json()[-1]["line"] == "Deployment failed"


def test_list_deployments_is_scoped_to_owned_app(deployment_client) -> None:
    client = deployment_client
    owner_headers = auth_headers(client, "owner@example.com")
    other_headers = auth_headers(client, "other@example.com")
    owner_app = create_app(client, owner_headers)
    other_app = create_app(client, other_headers)
    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulDeploymentSSHService()

    client.post(f"/api/v1/apps/{owner_app['id']}/deploy", headers=owner_headers)
    client.post(f"/api/v1/apps/{other_app['id']}/deploy", headers=other_headers)

    owner_list = client.get(f"/api/v1/apps/{owner_app['id']}/deployments", headers=owner_headers)
    other_list = client.get(f"/api/v1/apps/{owner_app['id']}/deployments", headers=other_headers)

    assert owner_list.status_code == 200
    assert len(owner_list.json()) == 1
    assert other_list.status_code == 404


def test_deployment_detail_and_logs_are_owner_scoped(deployment_client) -> None:
    client = deployment_client
    owner_headers = auth_headers(client, "owner@example.com")
    other_headers = auth_headers(client, "other@example.com")
    app_record = create_app(client, owner_headers)
    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulDeploymentSSHService()

    deployment = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=owner_headers).json()

    other_detail = client.get(f"/api/v1/deployments/{deployment['id']}", headers=other_headers)
    other_logs = client.get(f"/api/v1/deployments/{deployment['id']}/logs", headers=other_headers)

    assert other_detail.status_code == 404
    assert other_logs.status_code == 404


def test_deployment_stream_replays_logs_and_final_status(deployment_client) -> None:
    client = deployment_client
    headers = auth_headers(client, "owner@example.com")
    app_record = create_app(client, headers)
    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulDeploymentSSHService()
    deployment = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers).json()

    with client.stream("GET", f"/api/v1/deployments/{deployment['id']}/stream", headers=headers) as response:
        body = response.read().decode("utf-8")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'event: log\ndata: {"stream":"system","line":"Deployment started","sequence":1}' in body
    assert 'event: log\ndata: {"stream":"stdout","line":"pulling","sequence":3}' in body
    assert 'event: status\ndata: {"status":"success"}' in body


def test_deployment_stream_is_owner_scoped(deployment_client) -> None:
    client = deployment_client
    owner_headers = auth_headers(client, "owner@example.com")
    other_headers = auth_headers(client, "other@example.com")
    app_record = create_app(client, owner_headers)
    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulDeploymentSSHService()
    deployment = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=owner_headers).json()

    response = client.get(f"/api/v1/deployments/{deployment['id']}/stream", headers=other_headers)

    assert response.status_code == 404


async def test_rollback_creates_rollback_deployment_and_runs_checkout(deployment_client) -> None:
    client = deployment_client
    headers = auth_headers(client, "owner@example.com")
    app_record = create_app(client, headers)
    ssh_service = RollbackSSHService()
    app.dependency_overrides[get_ssh_service] = lambda: ssh_service
    first_deployment = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers).json()
    second_deployment = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers).json()

    rollback_response = client.post(f"/api/v1/deployments/{second_deployment['id']}/rollback", headers=headers)
    rollback_id = rollback_response.json()["id"]
    detail_response = client.get(f"/api/v1/deployments/{rollback_id}", headers=headers)
    logs_response = client.get(f"/api/v1/deployments/{rollback_id}/logs", headers=headers)

    assert first_deployment["kind"] == DeploymentKind.deploy.value
    assert rollback_response.status_code == 202
    assert rollback_response.json()["kind"] == DeploymentKind.rollback.value
    assert rollback_response.json()["commit_sha"] == "aaa111"
    assert rollback_response.json()["previous_commit_sha"] == "bbb222"
    detail = detail_response.json()
    assert detail["status"] == DeploymentStatus.success.value
    assert detail["commit_sha"] == "aaa111"
    assert [log["line"] for log in logs_response.json()] == [
        "Rollback started",
        "checked out",
        "restarted",
        "Rollback succeeded",
    ]
    assert any("git fetch" in call.command for call in ssh_service.calls)
    assert any("git checkout aaa111" in call.command for call in ssh_service.calls)
    assert all(call.private_key == TEST_PRIVATE_KEY for call in ssh_service.calls)

    async with deployment_client.async_session() as session:
        audit_log = (
            await session.execute(select(AuditLog).where(AuditLog.action == "rollback.started"))
        ).scalar_one()

    assert audit_log.entity_type == "deployment"
    assert audit_log.entity_id == rollback_id
    assert audit_log.metadata_json["source_deployment_id"] == second_deployment["id"]
    assert audit_log.metadata_json["target_commit"] == "aaa111"


def test_rollback_rejects_when_no_previous_successful_commit_exists(deployment_client) -> None:
    client = deployment_client
    headers = auth_headers(client, "owner@example.com")
    app_record = create_app(client, headers)
    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulDeploymentSSHService()
    deployment = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers).json()

    response = client.post(f"/api/v1/deployments/{deployment['id']}/rollback", headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "No previous successful deployment commit is available for rollback"


def test_rollback_is_owner_scoped(deployment_client) -> None:
    client = deployment_client
    owner_headers = auth_headers(client, "owner@example.com")
    other_headers = auth_headers(client, "other@example.com")
    app_record = create_app(client, owner_headers)
    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulDeploymentSSHService()
    deployment = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=owner_headers).json()

    response = client.post(f"/api/v1/deployments/{deployment['id']}/rollback", headers=other_headers)

    assert response.status_code == 404


def test_deploy_route_rejects_unauthenticated_requests(deployment_client) -> None:
    client = deployment_client

    response = client.post("/api/v1/apps/00000000-0000-0000-0000-000000000000/deploy")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


async def test_deploy_is_rejected_while_another_deployment_is_active(deployment_client) -> None:
    """A second deploy must be refused while one is still pending or running.

    The active deployment is seeded directly: TestClient runs FastAPI background
    tasks to completion before returning, so a real in-flight deploy cannot be
    observed mid-flight through the client.
    """
    client = deployment_client
    headers = auth_headers(client, "owner@example.com")
    app_record = create_app(client, headers)

    async with client.async_session() as session:
        owner = (await session.execute(select(User))).scalars().first()
        session.add(
            Deployment(
                owner_id=owner.id,
                app_id=uuid.UUID(app_record["id"]),
                server_id=uuid.UUID(app_record["server_id"]),
                status=DeploymentStatus.running,
                kind=DeploymentKind.deploy,
            )
        )
        await session.commit()

    response = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers)

    assert response.status_code == 409
    assert "already running" in response.json()["detail"]


async def test_rollback_is_rejected_while_another_deployment_is_active(deployment_client) -> None:
    client = deployment_client
    headers = auth_headers(client, "owner@example.com")
    app_record = create_app(client, headers)
    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulDeploymentSSHService()

    finished = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers).json()

    async with client.async_session() as session:
        owner = (await session.execute(select(User))).scalars().first()
        session.add(
            Deployment(
                owner_id=owner.id,
                app_id=uuid.UUID(app_record["id"]),
                server_id=uuid.UUID(app_record["server_id"]),
                status=DeploymentStatus.pending,
                kind=DeploymentKind.deploy,
            )
        )
        await session.commit()

    response = client.post(f"/api/v1/deployments/{finished['id']}/rollback", headers=headers)

    assert response.status_code == 409
    assert "already pending" in response.json()["detail"]


def test_deploy_is_allowed_again_after_the_previous_one_finishes(deployment_client) -> None:
    client = deployment_client
    headers = auth_headers(client, "owner@example.com")
    app_record = create_app(client, headers)
    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulDeploymentSSHService()

    first = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers)
    second = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
