"""GitHub webhook automation (spec §40-41): signature verification, replay
protection, branch validation, auto-deploy toggle, commit metadata."""

import hashlib
import hmac
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session, get_sessionmaker
from app.main import app
from app.models import App, Deployment, User
from app.models.deployment import DeploymentStatus
from app.services.ssh_service import SSHCommandResult, get_ssh_service

TEST_PRIVATE_KEY = """-----BEGIN OPENSSH PRIVATE KEY-----
test-private-key
-----END OPENSSH PRIVATE KEY-----"""


class SuccessfulSSH:
    async def run_command(self, *, command: str, **_) -> SSHCommandResult:
        if "git rev-parse HEAD" in command:
            return SSHCommandResult(exit_code=0, stdout="abc123\n", stderr="")
        return SSHCommandResult(exit_code=0, stdout="deployed\n", stderr="")


@pytest.fixture
async def webhook_client(monkeypatch):
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
    app.dependency_overrides[get_ssh_service] = lambda: SuccessfulSSH()

    with TestClient(app) as client:
        client.async_session = async_session
        yield client

    app.dependency_overrides.clear()
    get_settings.cache_clear()
    await engine.dispose()


def auth_headers(client: TestClient, email: str) -> dict[str, str]:
    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "strong-password", "full_name": "Owner"},
    )
    token = register_response.json()["token"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def setup_webhook_app(client: TestClient, headers: dict[str, str]) -> tuple[dict, str]:
    server = client.post(
        "/api/v1/servers",
        json={"name": "Prod", "host": "203.0.113.10", "port": 22, "username": "deploy", "private_key": TEST_PRIVATE_KEY},
        headers=headers,
    ).json()
    application = client.post(
        "/api/v1/apps",
        json={
            "name": "Watchdog",
            "server_id": server["id"],
            "repository_url": "https://github.com/example/watchdog.git",
            "branch": "main",
            "app_path": "/opt/watchdog",
            "deploy_command": "make build",
        },
        headers=headers,
    ).json()
    minted = client.post(f"/api/v1/apps/{application['id']}/webhook-secret", headers=headers)
    assert minted.status_code == 201
    return application, minted.json()["webhook_secret"]


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def push_payload(full_name: str, branch: str = "main", commit: str = "a81f92cdeadbeef", message: str = "fix: crash") -> dict:
    return {
        "ref": f"refs/heads/{branch}",
        "after": commit,
        "repository": {"full_name": full_name},
        "head_commit": {"message": message},
    }


def deliver(client: TestClient, secret: str, payload: dict, delivery_id: str = "d1", event: str = "push") -> object:
    body = json.dumps(payload).encode()
    return client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": event,
            "X-GitHub-Delivery": delivery_id,
            "X-Hub-Signature-256": sign(secret, body),
        },
    )


async def _deployments(client) -> list[Deployment]:
    async with client.async_session() as session:
        return list((await session.execute(select(Deployment))).scalars().all())


def test_verified_push_creates_deployment_with_commit_metadata(webhook_client) -> None:
    client = webhook_client
    headers = auth_headers(client, "owner@example.com")
    application, secret = setup_webhook_app(client, headers)

    response = deliver(client, secret, push_payload("example/watchdog"), delivery_id="d-100")

    assert response.status_code == 202
    assert response.json()["webhook_result"] == "deployed"
    assert response.json()["commit_sha"] == "a81f92cdeadbeef"
    assert response.json()["commit_message"] == "fix: crash"
    assert response.json()["triggered_by"] == "github-webhook"

    deployments = client.portal.start_task_soon(lambda: _deployments(client)).result(timeout=10)
    assert len(deployments) == 1
    assert deployments[0].commit_message == "fix: crash"


def test_wrong_signature_is_rejected_without_deploying(webhook_client) -> None:
    client = webhook_client
    headers = auth_headers(client, "owner@example.com")
    application, secret = setup_webhook_app(client, headers)

    body = json.dumps(push_payload("example/watchdog")).encode()
    response = client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": "d-2",
            "X-Hub-Signature-256": "sha256=" + "0" * 64,  # wrong signature
        },
    )

    assert response.status_code == 202
    assert response.json()["webhook_result"] == "rejected"
    deployments = client.portal.start_task_soon(lambda: _deployments(client)).result(timeout=10)
    assert deployments == []


def test_signature_is_required_even_when_secret_missing(webhook_client) -> None:
    client = webhook_client
    headers = auth_headers(client, "owner@example.com")
    application, secret = setup_webhook_app(client, headers)

    async def _strip_secret():
        async with client.async_session() as session:
            row = await session.get(App, uuid.UUID(application["id"]))
            row.encrypted_webhook_secret = None
            await session.commit()

    client.portal.start_task_soon(_strip_secret).result(timeout=10)

    unsigned = client.post(
        "/api/v1/webhooks/github",
        content=json.dumps(push_payload("example/watchdog")).encode(),
        headers={"X-GitHub-Event": "push", "X-GitHub-Delivery": "d-3"},
    )
    assert unsigned.json()["webhook_result"] == "rejected"


def test_branch_mismatch_is_ignored(webhook_client) -> None:
    client = webhook_client
    headers = auth_headers(client, "owner@example.com")
    application, secret = setup_webhook_app(client, headers)

    response = deliver(client, secret, push_payload("example/watchdog", branch="develop"), delivery_id="d-4")

    assert response.json()["webhook_result"] == "ignored"
    deployments = client.portal.start_task_soon(lambda: _deployments(client)).result(timeout=10)
    assert deployments == []


def test_duplicate_delivery_is_idempotent(webhook_client) -> None:
    client = webhook_client
    headers = auth_headers(client, "owner@example.com")
    application, secret = setup_webhook_app(client, headers)

    first = deliver(client, secret, push_payload("example/watchdog"), delivery_id="d-5")
    replay = deliver(client, secret, push_payload("example/watchdog"), delivery_id="d-5")

    assert first.json()["webhook_result"] == "deployed"
    assert replay.json()["webhook_result"] == "ignored"
    deployments = client.portal.start_task_soon(lambda: _deployments(client)).result(timeout=10)
    assert len(deployments) == 1  # no second deployment from the replay


def test_ping_is_acknowledged_and_auto_deploy_toggle_respected(webhook_client) -> None:
    client = webhook_client
    headers = auth_headers(client, "owner@example.com")
    application, secret = setup_webhook_app(client, headers)

    ping = client.post(
        "/api/v1/webhooks/github",
        content=b"{}",
        headers={
            "X-GitHub-Event": "ping",
            "X-GitHub-Delivery": "d-6",
            "X-Hub-Signature-256": sign(secret, b"{}"),
        },
    )
    assert ping.json()["webhook_result"] == "ignored"

    async def _disable():
        async with client.async_session() as session:
            row = await session.get(App, uuid.UUID(application["id"]))
            row.auto_deploy = False
            await session.commit()

    client.portal.start_task_soon(_disable).result(timeout=10)

    disabled = deliver(client, secret, push_payload("example/watchdog"), delivery_id="d-7")
    assert disabled.json()["webhook_result"] == "ignored"


def test_push_while_active_queues_instead_of_failing(webhook_client) -> None:
    """Spec §42: automatic deployments queue behind an active deployment."""
    client = webhook_client
    headers = auth_headers(client, "owner@example.com")
    application, secret = setup_webhook_app(client, headers)

    # Seed an in-flight deployment so the push has something to queue behind
    # (the SSH stub would otherwise finish it instantly).
    async def _seed_active():
        async with client.async_session() as session:
            owner = (await session.execute(select(User))).scalar_one()
            deployment = Deployment(
                owner_id=owner.id,
                app_id=uuid.UUID(application["id"]),
                server_id=uuid.UUID(application["server_id"]),
                status=DeploymentStatus.running,
                triggered_by="ui",
            )
            session.add(deployment)
            await session.commit()

    client.portal.start_task_soon(_seed_active).result(timeout=10)

    pushed = deliver(client, secret, push_payload("example/watchdog", commit="2222222"), delivery_id="d-9")
    assert pushed.status_code == 202
    assert pushed.json()["status"] == DeploymentStatus.queued.value
    assert pushed.json()["commit_sha"] == "2222222"
    assert pushed.json()["webhook_result"] == "queued"
