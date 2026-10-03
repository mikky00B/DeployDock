"""Environments, environment variables, and domains (spec §12, §36, §38)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.encryption import decrypt_text
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models import EnvironmentVariable

TEST_PRIVATE_KEY = """-----BEGIN OPENSSH PRIVATE KEY-----
test-private-key
-----END OPENSSH PRIVATE KEY-----"""


@pytest.fixture
async def env_client(monkeypatch):
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
        json={"email": email, "password": "strong-password", "full_name": "Owner"},
    )
    token = register_response.json()["token"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def setup_app(client: TestClient, headers: dict[str, str]) -> dict:
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
    return {"server": server, "app": application}


def test_environment_crud_is_app_scoped(env_client) -> None:
    client = env_client
    headers = auth_headers(client, "owner@example.com")
    data = setup_app(client, headers)

    created = client.post(
        f"/api/v1/apps/{data['app']['id']}/environments",
        json={"name": "production", "server_id": data["server"]["id"]},
        headers=headers,
    )
    assert created.status_code == 201
    environment = created.json()
    assert environment["name"] == "production"
    assert environment["auto_deploy"] is True

    listed = client.get(f"/api/v1/apps/{data['app']['id']}/environments", headers=headers)
    assert [env["name"] for env in listed.json()] == ["production"]

    # Duplicate names are rejected per app.
    duplicate = client.post(
        f"/api/v1/apps/{data['app']['id']}/environments",
        json={"name": "production", "server_id": data["server"]["id"]},
        headers=headers,
    )
    assert duplicate.status_code == 409

    # Names must be slugs.
    bad_name = client.post(
        f"/api/v1/apps/{data['app']['id']}/environments",
        json={"name": "Not A Slug", "server_id": data["server"]["id"]},
        headers=headers,
    )
    assert bad_name.status_code == 422

    deleted = client.delete(f"/api/v1/environments/{environment['id']}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/environments/{environment['id']}", headers=headers).status_code == 404


def test_environment_requires_owned_server_and_matching_app_server(env_client) -> None:
    client = env_client
    headers = auth_headers(client, "owner@example.com")
    data = setup_app(client, headers)

    other_server = client.post(
        "/api/v1/servers",
        json={"name": "Other", "host": "198.51.100.1", "port": 22, "username": "deploy", "private_key": TEST_PRIVATE_KEY},
        headers=headers,
    ).json()
    mismatch = client.post(
        f"/api/v1/apps/{data['app']['id']}/environments",
        json={"name": "staging", "server_id": other_server["id"]},
        headers=headers,
    )
    assert mismatch.status_code == 400

    unknown = client.post(
        f"/api/v1/apps/{data['app']['id']}/environments",
        json={"name": "staging", "server_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert unknown.status_code == 404


def test_variables_are_encrypted_and_masked(env_client) -> None:
    client = env_client
    headers = auth_headers(client, "owner@example.com")
    data = setup_app(client, headers)
    environment = client.post(
        f"/api/v1/apps/{data['app']['id']}/environments",
        json={"name": "production", "server_id": data["server"]["id"]},
        headers=headers,
    ).json()
    environment_id = environment["id"]

    put = client.put(
        f"/api/v1/environments/{environment_id}/variables/DATABASE_URL",
        json={"key": "DATABASE_URL", "value": "postgres://secret-connection-string"},
        headers=headers,
    )
    assert put.status_code == 200

    listed = client.get(f"/api/v1/environments/{environment_id}/variables", headers=headers)
    assert listed.status_code == 200
    keys = [variable["key"] for variable in listed.json()]
    assert keys == ["DATABASE_URL"]
    # The plaintext must not leak through the masked read.
    assert "secret-connection-string" not in listed.text
    assert "value" not in listed.json()[0]

    # Stored encrypted at rest.
    async def _read_stored():
        async with client.async_session() as session:
            row = (await session.execute(select(EnvironmentVariable))).scalar_one()
            return row.encrypted_value

    stored = client.portal.start_task_soon(_read_stored).result(timeout=10)
    assert "secret-connection-string" not in stored
    assert decrypt_text(stored, "test-encryption-key") == "postgres://secret-connection-string"

    # Unset removes the variable.
    unset = client.delete(
        f"/api/v1/environments/{environment_id}/variables/DATABASE_URL", headers=headers
    )
    assert unset.status_code == 204
    assert client.get(f"/api/v1/environments/{environment_id}/variables", headers=headers).json() == []

    # Unsetting an unknown key 404s.
    missing = client.delete(
        f"/api/v1/environments/{environment_id}/variables/NOPE", headers=headers
    )
    assert missing.status_code == 404


def test_domains_add_and_verify_dns(env_client, monkeypatch) -> None:
    from app.services import environment_service

    client = env_client
    headers = auth_headers(client, "owner@example.com")
    data = setup_app(client, headers)
    environment = client.post(
        f"/api/v1/apps/{data['app']['id']}/environments",
        json={"name": "production", "server_id": data["server"]["id"]},
        headers=headers,
    ).json()

    added = client.post(
        f"/api/v1/environments/{environment['id']}/domains",
        json={"hostname": "Watchdog.Example.com"},
        headers=headers,
    )
    assert added.status_code == 201
    domain = added.json()
    assert domain["hostname"] == "watchdog.example.com"  # normalized
    assert domain["status"] == "pending"

    # Point the domain at the server's host IP.
    monkeypatch.setattr(environment_service, "_resolve", lambda host: {"203.0.113.10"})
    verified = client.post(f"/api/v1/domains/{domain['id']}/verify", headers=headers)
    assert verified.status_code == 200
    body = verified.json()
    assert body["verified"] is True

    # A mismatch fails verification with a readable error.
    monkeypatch.setattr(
        environment_service, "_resolve", lambda host: {"198.51.100.99"} if host != "203.0.113.10" else {"203.0.113.10"}
    )
    failed = client.post(f"/api/v1/domains/{domain['id']}/verify", headers=headers)
    assert failed.json()["verified"] is False

    listing = client.get(f"/api/v1/environments/{environment['id']}/domains", headers=headers)
    assert [d["hostname"] for d in listing.json()] == ["watchdog.example.com"]


def test_endpoints_require_authentication(env_client) -> None:
    client = env_client
    headers = auth_headers(client, "owner@example.com")
    data = setup_app(client, headers)

    no_auth = client.get(f"/api/v1/apps/{data['app']['id']}/environments")
    assert no_auth.status_code == 401

    # Owner scoping: another user sees nothing.
    other = auth_headers(client, "other@example.com")
    forbidden = client.get(f"/api/v1/environments/{uuid.uuid4()}", headers=other)
    assert forbidden.status_code == 404
