import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models import AuditLog
from app.services.ssh_service import SSHCommandResult, get_ssh_service

TEST_PRIVATE_KEY = """-----BEGIN OPENSSH PRIVATE KEY-----
test-private-key
-----END OPENSSH PRIVATE KEY-----"""


@pytest.fixture
async def app_client(monkeypatch):
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


def create_server(client: TestClient, headers: dict[str, str], name: str = "Main VPS") -> dict[str, object]:
    response = client.post(
        "/api/v1/servers",
        json={
            "name": name,
            "host": "203.0.113.10",
            "port": 22,
            "username": "deploy",
            "private_key": TEST_PRIVATE_KEY,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def app_payload(server_id: str, name: str = "Watchdog") -> dict[str, object]:
    return {
        "name": name,
        "server_id": server_id,
        "repository_url": "https://github.com/example/watchdog.git",
        "branch": "main",
        "app_path": "/opt/watchdog",
        "service_name": "watchdog",
        "deploy_command": "set -e\ngit pull origin main\nsudo systemctl restart watchdog",
        "restart_command": "sudo systemctl restart watchdog",
        "healthcheck_url": "https://watchdog.example.com/health",
    }


class RecordingSSHService:
    def __init__(self, result: SSHCommandResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

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
        self.calls.append(
            {
                "host": host,
                "port": port,
                "username": username,
                "private_key": private_key,
                "command": command,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.result


class RaisingSSHService:
    async def run_command(self, **_) -> SSHCommandResult:
        raise RuntimeError("connection refused")


def test_create_app_attached_to_owned_server(app_client) -> None:
    client = app_client
    headers = auth_headers(client, "owner@example.com")
    server = create_server(client, headers)

    response = client.post("/api/v1/apps", json=app_payload(server["id"]), headers=headers)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Watchdog"
    assert data["server_id"] == server["id"]
    assert data["branch"] == "main"
    assert data["deploy_command"].startswith("set -e")
    assert data["current_commit"] is None
    assert data["last_successful_commit"] is None


def test_create_app_rejects_another_users_server(app_client) -> None:
    client = app_client
    owner_headers = auth_headers(client, "owner@example.com")
    other_headers = auth_headers(client, "other@example.com")
    other_server = create_server(client, other_headers, "Other VPS")

    response = client.post("/api/v1/apps", json=app_payload(other_server["id"]), headers=owner_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Server not found"


def test_list_and_show_only_return_current_users_apps(app_client) -> None:
    client = app_client
    owner_headers = auth_headers(client, "owner@example.com")
    other_headers = auth_headers(client, "other@example.com")
    owner_server = create_server(client, owner_headers)
    other_server = create_server(client, other_headers, "Other VPS")

    owner_app = client.post("/api/v1/apps", json=app_payload(owner_server["id"], "Owner App"), headers=owner_headers).json()
    client.post("/api/v1/apps", json=app_payload(other_server["id"], "Other App"), headers=other_headers)

    owner_list = client.get("/api/v1/apps", headers=owner_headers)
    other_show = client.get(f"/api/v1/apps/{owner_app['id']}", headers=other_headers)

    assert owner_list.status_code == 200
    assert [item["name"] for item in owner_list.json()] == ["Owner App"]
    assert other_show.status_code == 404


def test_update_app_validates_new_server_ownership(app_client) -> None:
    client = app_client
    owner_headers = auth_headers(client, "owner@example.com")
    other_headers = auth_headers(client, "other@example.com")
    owner_server = create_server(client, owner_headers)
    other_server = create_server(client, other_headers, "Other VPS")
    created = client.post("/api/v1/apps", json=app_payload(owner_server["id"]), headers=owner_headers).json()

    rejected = client.patch(
        f"/api/v1/apps/{created['id']}",
        json={"server_id": other_server["id"]},
        headers=owner_headers,
    )
    updated = client.patch(
        f"/api/v1/apps/{created['id']}",
        json={"name": "Watchdog API", "deploy_command": "set -e\n./deploy.sh"},
        headers=owner_headers,
    )

    assert rejected.status_code == 404
    assert rejected.json()["detail"] == "Server not found"
    assert updated.status_code == 200
    assert updated.json()["name"] == "Watchdog API"
    assert updated.json()["deploy_command"] == "set -e\n./deploy.sh"


def test_delete_app_removes_only_owned_app(app_client) -> None:
    client = app_client
    owner_headers = auth_headers(client, "owner@example.com")
    other_headers = auth_headers(client, "other@example.com")
    owner_server = create_server(client, owner_headers)
    created = client.post("/api/v1/apps", json=app_payload(owner_server["id"]), headers=owner_headers).json()

    other_delete = client.delete(f"/api/v1/apps/{created['id']}", headers=other_headers)
    owner_delete = client.delete(f"/api/v1/apps/{created['id']}", headers=owner_headers)
    owner_show = client.get(f"/api/v1/apps/{created['id']}", headers=owner_headers)

    assert other_delete.status_code == 404
    assert owner_delete.status_code == 204
    assert owner_show.status_code == 404


def test_app_rejects_blank_deploy_command(app_client) -> None:
    client = app_client
    headers = auth_headers(client, "owner@example.com")
    server = create_server(client, headers)
    payload = app_payload(server["id"])
    payload["deploy_command"] = "   "

    response = client.post("/api/v1/apps", json=payload, headers=headers)

    assert response.status_code == 422


def test_app_routes_reject_unauthenticated_requests(app_client) -> None:
    client = app_client

    response = client.get("/api/v1/apps")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_service_status_runs_systemctl_for_owned_app(app_client) -> None:
    client = app_client
    headers = auth_headers(client, "owner@example.com")
    server = create_server(client, headers)
    created = client.post("/api/v1/apps", json=app_payload(server["id"]), headers=headers).json()
    ssh_service = RecordingSSHService(SSHCommandResult(exit_code=0, stdout="active\n", stderr=""))
    app.dependency_overrides[get_ssh_service] = lambda: ssh_service

    response = client.get(f"/api/v1/apps/{created['id']}/status", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"service_name": "watchdog", "status": "active"}
    assert ssh_service.calls[0]["private_key"] == TEST_PRIVATE_KEY
    assert ssh_service.calls[0]["command"] == "systemctl is-active 'watchdog'"


async def test_restart_runs_command_and_writes_audit_log(app_client) -> None:
    client = app_client
    headers = auth_headers(client, "owner@example.com")
    server = create_server(client, headers)
    created = client.post("/api/v1/apps", json=app_payload(server["id"]), headers=headers).json()
    ssh_service = RecordingSSHService(SSHCommandResult(exit_code=0, stdout="restarted\n", stderr=""))
    app.dependency_overrides[get_ssh_service] = lambda: ssh_service

    response = client.post(f"/api/v1/apps/{created['id']}/restart", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "service_name": "watchdog",
        "success": True,
        "exit_code": 0,
        "message": "restarted",
    }
    assert ssh_service.calls[0]["command"] == "sudo systemctl restart watchdog"

    async with app_client.async_session() as session:
        audit_log = (
            await session.execute(select(AuditLog).where(AuditLog.action == "service.restarted"))
        ).scalar_one()

    assert audit_log.action == "service.restarted"
    assert audit_log.entity_type == "app"
    assert audit_log.entity_id == created["id"]
    assert audit_log.metadata_json == {
        "service_name": "watchdog",
        "exit_code": 0,
        "success": True,
    }


def test_service_logs_runs_journalctl(app_client) -> None:
    client = app_client
    headers = auth_headers(client, "owner@example.com")
    server = create_server(client, headers)
    created = client.post("/api/v1/apps", json=app_payload(server["id"]), headers=headers).json()
    ssh_service = RecordingSSHService(SSHCommandResult(exit_code=0, stdout="line one\nline two\n", stderr=""))
    app.dependency_overrides[get_ssh_service] = lambda: ssh_service

    response = client.get(f"/api/v1/apps/{created['id']}/logs", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"service_name": "watchdog", "logs": "line one\nline two\n"}
    assert ssh_service.calls[0]["command"] == "journalctl -u 'watchdog' -n 100 --no-pager"


def test_service_status_returns_safe_error_when_ssh_fails(app_client) -> None:
    client = app_client
    headers = auth_headers(client, "owner@example.com")
    server = create_server(client, headers)
    created = client.post("/api/v1/apps", json=app_payload(server["id"]), headers=headers).json()
    app.dependency_overrides[get_ssh_service] = lambda: RaisingSSHService()

    response = client.get(f"/api/v1/apps/{created['id']}/status", headers=headers)

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail.startswith("Could not run the command on 203.0.113.10:")
    # Library exception internals must not leak into the response.
    assert "connection refused" not in detail


def test_service_operations_are_owner_scoped(app_client) -> None:
    client = app_client
    owner_headers = auth_headers(client, "owner@example.com")
    other_headers = auth_headers(client, "other@example.com")
    server = create_server(client, owner_headers)
    created = client.post("/api/v1/apps", json=app_payload(server["id"]), headers=owner_headers).json()
    app.dependency_overrides[get_ssh_service] = lambda: RecordingSSHService(
        SSHCommandResult(exit_code=0, stdout="active\n", stderr="")
    )

    response = client.get(f"/api/v1/apps/{created['id']}/status", headers=other_headers)

    assert response.status_code == 404


def test_service_logs_rejects_app_without_service_name(app_client) -> None:
    client = app_client
    headers = auth_headers(client, "owner@example.com")
    server = create_server(client, headers)
    payload = app_payload(server["id"])
    payload["service_name"] = None
    payload["restart_command"] = None
    created = client.post("/api/v1/apps", json=payload, headers=headers).json()

    logs_response = client.get(f"/api/v1/apps/{created['id']}/logs", headers=headers)
    restart_response = client.post(f"/api/v1/apps/{created['id']}/restart", headers=headers)

    assert logs_response.status_code == 400
    assert logs_response.json()["detail"] == "App does not have a service name"
    assert restart_response.status_code == 400
    assert restart_response.json()["detail"] == "App does not have a restart command or service name"
