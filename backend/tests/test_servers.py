from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.encryption import decrypt_text
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models import AuditLog, Server
from app.models.server import ServerStatus
from app.services.ssh_service import HostKeyInfo, SSHCommandResult, get_ssh_service

TEST_PRIVATE_KEY = """-----BEGIN OPENSSH PRIVATE KEY-----
test-private-key
-----END OPENSSH PRIVATE KEY-----"""


@dataclass
class SSHCall:
    host: str
    port: int
    username: str
    private_key: str
    command: str


TEST_HOST_KEY = HostKeyInfo(
    algorithm="ssh-ed25519",
    base64_key="AAAAC3NzaC1lZDI1NTE5AAAAIGtestkeytestkeytestkeytestkeytestkey0",
    fingerprint="SHA256:testhostkeyfingerprint",
)


class SuccessfulSSHService:
    def __init__(self) -> None:
        self.calls: list[SSHCall] = []

    async def scan_host_key(self, *, host: str, port: int, timeout_seconds: int = 15) -> HostKeyInfo:
        return TEST_HOST_KEY

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
        self.calls.append(SSHCall(host, port, username, private_key, command))
        return SSHCommandResult(exit_code=0, stdout="deploydock-ok\n", stderr="")


class FailingSSHService:
    async def scan_host_key(self, *, host: str, port: int, timeout_seconds: int = 15) -> HostKeyInfo:
        return TEST_HOST_KEY

    async def run_command(self, **_) -> SSHCommandResult:
        raise RuntimeError("authentication failed for deploy@203.0.113.10")


@pytest.fixture
async def server_client(monkeypatch):
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
        yield client, async_session

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


def server_payload(name: str = "Main VPS") -> dict[str, object]:
    return {
        "name": name,
        "host": "203.0.113.10",
        "port": 22,
        "username": "deploy",
        "private_key": TEST_PRIVATE_KEY,
    }


async def test_create_server_encrypts_private_key_and_redacts_response(server_client) -> None:
    client, async_session = server_client
    headers = auth_headers(client, "owner@example.com")

    response = client.post("/api/v1/servers", json=server_payload(), headers=headers)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Main VPS"
    assert data["status"] == "unknown"
    assert data["private_key_fingerprint"].startswith("SHA256:")
    assert "private_key" not in data
    assert "encrypted_private_key" not in data

    async with async_session() as session:
        stored_server = (await session.execute(select(Server))).scalar_one()

    assert stored_server.encrypted_private_key != TEST_PRIVATE_KEY
    assert TEST_PRIVATE_KEY not in stored_server.encrypted_private_key
    assert decrypt_text(stored_server.encrypted_private_key, "test-encryption-key") == TEST_PRIVATE_KEY


async def test_create_server_generates_unique_keypair_by_default(server_client) -> None:
    client, async_session = server_client
    headers = auth_headers(client, "owner@example.com")
    payload = server_payload()
    payload.pop("private_key")

    first_response = client.post("/api/v1/servers", json=payload, headers=headers)
    second_response = client.post("/api/v1/servers", json={**payload, "name": "Second VPS"}, headers=headers)

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    first = first_response.json()
    second = second_response.json()
    assert first["public_ssh_key"].startswith("ssh-ed25519 ")
    assert second["public_ssh_key"].startswith("ssh-ed25519 ")
    assert first["public_ssh_key"] != second["public_ssh_key"]
    assert "private_key" not in first
    assert "encrypted_private_key" not in first

    async with async_session() as session:
        stored_servers = list((await session.execute(select(Server).order_by(Server.name))).scalars().all())

    decrypted_keys = [
        decrypt_text(stored_server.encrypted_private_key, "test-encryption-key")
        for stored_server in stored_servers
    ]
    assert all(key.startswith("-----BEGIN OPENSSH PRIVATE KEY-----") for key in decrypted_keys)
    assert decrypted_keys[0] != decrypted_keys[1]


def test_list_and_show_only_return_current_users_servers(server_client) -> None:
    client, _ = server_client
    owner_headers = auth_headers(client, "owner@example.com")
    other_headers = auth_headers(client, "other@example.com")

    owner_server = client.post("/api/v1/servers", json=server_payload("Owner VPS"), headers=owner_headers).json()
    client.post("/api/v1/servers", json=server_payload("Other VPS"), headers=other_headers)

    owner_list = client.get("/api/v1/servers", headers=owner_headers)
    other_show = client.get(f"/api/v1/servers/{owner_server['id']}", headers=other_headers)

    assert owner_list.status_code == 200
    assert [server["name"] for server in owner_list.json()] == ["Owner VPS"]
    assert other_show.status_code == 404


def test_update_server_can_replace_private_key_without_exposing_it(server_client) -> None:
    client, _ = server_client
    headers = auth_headers(client, "owner@example.com")
    created = client.post("/api/v1/servers", json=server_payload(), headers=headers).json()
    new_private_key = "-----BEGIN OPENSSH PRIVATE KEY-----\nnew-key\n-----END OPENSSH PRIVATE KEY-----"

    response = client.patch(
        f"/api/v1/servers/{created['id']}",
        json={"name": "Renamed VPS", "private_key": new_private_key},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Renamed VPS"
    assert data["status"] == "unknown"
    assert "private_key" not in data
    assert "encrypted_private_key" not in data


def test_delete_server_removes_only_owned_server(server_client) -> None:
    client, _ = server_client
    owner_headers = auth_headers(client, "owner@example.com")
    other_headers = auth_headers(client, "other@example.com")
    created = client.post("/api/v1/servers", json=server_payload(), headers=owner_headers).json()

    other_delete = client.delete(f"/api/v1/servers/{created['id']}", headers=other_headers)
    owner_delete = client.delete(f"/api/v1/servers/{created['id']}", headers=owner_headers)
    owner_show = client.get(f"/api/v1/servers/{created['id']}", headers=owner_headers)

    assert other_delete.status_code == 404
    assert owner_delete.status_code == 204
    assert owner_show.status_code == 404


def test_server_routes_reject_unauthenticated_requests(server_client) -> None:
    client, _ = server_client

    response = client.get("/api/v1/servers")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_connection_test_uses_decrypted_key_and_marks_connected(server_client) -> None:
    client, _ = server_client
    headers = auth_headers(client, "owner@example.com")
    created = client.post("/api/v1/servers", json=server_payload(), headers=headers).json()
    ssh_service = SuccessfulSSHService()
    app.dependency_overrides[get_ssh_service] = lambda: ssh_service

    response = client.post(f"/api/v1/servers/{created['id']}/test-connection", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "status": ServerStatus.connected.value,
        "message": "SSH connection succeeded",
        "host_key_fingerprint": TEST_HOST_KEY.fingerprint,
    }
    assert ssh_service.calls == [
        SSHCall(
            host="203.0.113.10",
            port=22,
            username="deploy",
            private_key=TEST_PRIVATE_KEY,
            command="echo deploydock-ok",
        )
    ]


def test_connection_test_marks_unreachable_on_ssh_failure(server_client) -> None:
    client, _ = server_client
    headers = auth_headers(client, "owner@example.com")
    created = client.post("/api/v1/servers", json=server_payload(), headers=headers).json()
    app.dependency_overrides[get_ssh_service] = lambda: FailingSSHService()

    response = client.post(f"/api/v1/servers/{created['id']}/test-connection", headers=headers)

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["status"] == ServerStatus.unreachable.value
    assert "authentication failed" in response.json()["message"]


class RotatedHostKeySSHService:
    """Presents a different host key than the one already pinned."""

    ROTATED = HostKeyInfo(
        algorithm="ssh-ed25519",
        base64_key="AAAAC3NzaC1lZDI1NTE5AAAAIGrotatedrotatedrotatedrotatedrotate1",
        fingerprint="SHA256:rotatedhostkeyfingerprint",
    )

    async def scan_host_key(self, *, host: str, port: int, timeout_seconds: int = 15) -> HostKeyInfo:
        return self.ROTATED

    async def run_command(self, **_) -> SSHCommandResult:
        return SSHCommandResult(exit_code=0, stdout="deploydock-ok\n", stderr="")


class UnreachableHostKeySSHService:
    async def scan_host_key(self, *, host: str, port: int, timeout_seconds: int = 15) -> HostKeyInfo:
        raise ConnectionError("connection refused")

    async def run_command(self, **_) -> SSHCommandResult:  # pragma: no cover - never reached
        raise AssertionError("run_command must not be called when the host key scan fails")


async def test_connection_test_pins_the_host_key_on_first_use(server_client) -> None:
    client, async_session = server_client
    headers = auth_headers(client, "owner@example.com")
    created = client.post("/api/v1/servers", json=server_payload(), headers=headers).json()
    assert created["known_host_key_fingerprint"] is None

    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulSSHService()
    response = client.post(f"/api/v1/servers/{created['id']}/test-connection", headers=headers)

    assert response.status_code == 200
    assert response.json()["host_key_fingerprint"] == TEST_HOST_KEY.fingerprint

    async with async_session() as session:
        stored = (await session.execute(select(Server))).scalar_one()

    assert stored.known_host_key == TEST_HOST_KEY.stored_value
    assert stored.known_host_key_pinned_at is not None


async def test_connection_test_passes_the_pinned_key_to_the_ssh_layer(server_client) -> None:
    client, _ = server_client
    headers = auth_headers(client, "owner@example.com")
    created = client.post("/api/v1/servers", json=server_payload(), headers=headers).json()
    ssh_service = SuccessfulSSHService()
    app.dependency_overrides[get_ssh_service] = lambda: ssh_service

    client.post(f"/api/v1/servers/{created['id']}/test-connection", headers=headers)
    client.post(f"/api/v1/servers/{created['id']}/test-connection", headers=headers)

    assert len(ssh_service.calls) == 2


async def test_connection_test_reports_a_failed_host_key_scan(server_client) -> None:
    client, _ = server_client
    headers = auth_headers(client, "owner@example.com")
    created = client.post("/api/v1/servers", json=server_payload(), headers=headers).json()
    app.dependency_overrides[get_ssh_service] = lambda: UnreachableHostKeySSHService()

    response = client.post(f"/api/v1/servers/{created['id']}/test-connection", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["status"] == ServerStatus.unreachable.value
    assert "Could not read host key" in body["message"]


async def test_repin_host_key_replaces_the_pin_and_reports_the_previous_one(server_client) -> None:
    client, async_session = server_client
    headers = auth_headers(client, "owner@example.com")
    created = client.post("/api/v1/servers", json=server_payload(), headers=headers).json()

    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulSSHService()
    client.post(f"/api/v1/servers/{created['id']}/test-connection", headers=headers)

    app.dependency_overrides[get_ssh_service] = lambda: RotatedHostKeySSHService()
    response = client.post(f"/api/v1/servers/{created['id']}/host-key", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["fingerprint"] == RotatedHostKeySSHService.ROTATED.fingerprint
    assert body["previous_fingerprint"] == TEST_HOST_KEY.fingerprint

    async with async_session() as session:
        stored = (await session.execute(select(Server))).scalar_one()

    assert stored.known_host_key == RotatedHostKeySSHService.ROTATED.stored_value
    assert stored.status == ServerStatus.unknown


async def test_repin_host_key_writes_an_audit_log(server_client) -> None:
    client, async_session = server_client
    headers = auth_headers(client, "owner@example.com")
    created = client.post("/api/v1/servers", json=server_payload(), headers=headers).json()
    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulSSHService()

    client.post(f"/api/v1/servers/{created['id']}/host-key", headers=headers)

    async with async_session() as session:
        actions = [
            log.action for log in (await session.execute(select(AuditLog))).scalars().all()
        ]

    assert "server.host_key_pinned" in actions


async def test_repin_host_key_reports_an_unreachable_server(server_client) -> None:
    client, _ = server_client
    headers = auth_headers(client, "owner@example.com")
    created = client.post("/api/v1/servers", json=server_payload(), headers=headers).json()
    app.dependency_overrides[get_ssh_service] = lambda: UnreachableHostKeySSHService()

    response = client.post(f"/api/v1/servers/{created['id']}/host-key", headers=headers)

    assert response.status_code == 502
    assert "Could not read a host key" in response.json()["detail"]
    # Library exception internals must not leak into the response.
    assert "UnreachableHostKey" not in response.json()["detail"]


async def test_repin_host_key_is_owner_scoped(server_client) -> None:
    client, _ = server_client
    owner_headers = auth_headers(client, "owner@example.com")
    created = client.post("/api/v1/servers", json=server_payload(), headers=owner_headers).json()
    other_headers = auth_headers(client, "intruder@example.com")
    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulSSHService()

    response = client.post(f"/api/v1/servers/{created['id']}/host-key", headers=other_headers)

    assert response.status_code == 404


async def test_changing_the_host_clears_the_pinned_key(server_client) -> None:
    client, async_session = server_client
    headers = auth_headers(client, "owner@example.com")
    created = client.post("/api/v1/servers", json=server_payload(), headers=headers).json()
    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulSSHService()
    client.post(f"/api/v1/servers/{created['id']}/test-connection", headers=headers)

    response = client.patch(
        f"/api/v1/servers/{created['id']}",
        json={"host": "203.0.113.99"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["known_host_key_fingerprint"] is None

    async with async_session() as session:
        stored = (await session.execute(select(Server))).scalar_one()

    assert stored.known_host_key is None
    assert stored.status == ServerStatus.unknown


async def test_renaming_a_server_keeps_the_pinned_key(server_client) -> None:
    client, _ = server_client
    headers = auth_headers(client, "owner@example.com")
    created = client.post("/api/v1/servers", json=server_payload(), headers=headers).json()
    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulSSHService()
    client.post(f"/api/v1/servers/{created['id']}/test-connection", headers=headers)

    response = client.patch(
        f"/api/v1/servers/{created['id']}",
        json={"name": "Renamed VPS"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["known_host_key_fingerprint"] == TEST_HOST_KEY.fingerprint
