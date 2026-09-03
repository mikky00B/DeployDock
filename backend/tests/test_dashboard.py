import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models import App, Deployment, Server
from app.models.deployment import DeploymentStatus
from app.models.server import ServerStatus

TEST_PRIVATE_KEY = """-----BEGIN OPENSSH PRIVATE KEY-----
test-private-key
-----END OPENSSH PRIVATE KEY-----"""


@pytest.fixture
async def dashboard_client(monkeypatch):
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


def create_app(client: TestClient, headers: dict[str, str], server_id: str, name: str = "Watchdog") -> dict[str, object]:
    response = client.post(
        "/api/v1/apps",
        json={
            "name": name,
            "server_id": server_id,
            "repository_url": "https://github.com/example/watchdog.git",
            "branch": "main",
            "app_path": "/opt/watchdog",
            "service_name": "watchdog",
            "deploy_command": "git pull origin main",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_dashboard_summarizes_only_current_user_resources(dashboard_client) -> None:
    client = dashboard_client
    owner_headers = auth_headers(client, "owner@example.com")
    other_headers = auth_headers(client, "other@example.com")
    owner_server = create_server(client, owner_headers)
    create_server(client, other_headers, "Other VPS")
    owner_app = create_app(client, owner_headers, owner_server["id"])

    async with client.async_session() as session:
        server = (await session.execute(select(Server).where(Server.id == uuid.UUID(owner_server["id"])))).scalar_one()
        app_record = (await session.execute(select(App).where(App.id == uuid.UUID(owner_app["id"])))).scalar_one()
        server.status = ServerStatus.connected
        app_record.last_successful_commit = "abc123"
        session.add(
            Deployment(
                owner_id=app_record.owner_id,
                app_id=app_record.id,
                server_id=server.id,
                status=DeploymentStatus.failed,
                commit_sha="def456",
            )
        )
        await session.commit()

    response = client.get("/api/v1/dashboard", headers=owner_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == {
        "total_servers": 1,
        "connected_servers": 1,
        "total_apps": 1,
        "deployed_apps": 1,
        "recent_failures": 1,
        "latest_deployment_status": "failed",
    }
    assert [server["name"] for server in data["recent_servers"]] == ["Main VPS"]
    assert [app["name"] for app in data["recent_apps"]] == ["Watchdog"]
    assert data["recent_deployments"][0]["status"] == "failed"
    assert {event["action"] for event in data["recent_audit_logs"]} >= {"server.created", "app.created"}


def test_dashboard_rejects_unauthenticated_requests(dashboard_client) -> None:
    response = dashboard_client.get("/api/v1/dashboard")

    assert response.status_code == 401
