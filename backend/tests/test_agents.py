from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models import Agent, AgentRegistrationToken, AuditLog
from app.services.agent_service import hash_token


@pytest.fixture
async def agent_client(monkeypatch):
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
        json={"email": email, "password": "strong-password", "full_name": "Owner"},
    )
    token = register_response.json()["token"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def mint_registration_token(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post("/api/v1/agents/registration-tokens", json={}, headers=headers)
    assert response.status_code == 201
    return response.json()


def register_agent(client: TestClient, registration_token: str, **overrides) -> dict:
    payload = {"name": "nyc-1.vps", "agent_version": "0.1.0", "os": "linux", "arch": "amd64"}
    payload.update(overrides)
    response = client.post(
        "/api/v1/agents/register",
        json=payload,
        headers={"Authorization": f"Bearer {registration_token}"},
    )
    return response


async def test_full_registration_flow(agent_client) -> None:
    client, async_session = agent_client
    headers = auth_headers(client, "owner@example.com")

    minted = mint_registration_token(client, headers)
    assert minted["token"].startswith("dck_rt_")
    registered = register_agent(client, minted["token"])

    assert registered.status_code == 201
    data = registered.json()
    assert data["agent_token"].startswith("dck_at_")
    assert data["heartbeat_interval_seconds"] == 30

    async with async_session() as session:
        agent = (await session.execute(select(Agent))).scalar_one()
        registration_rows = list((await session.execute(select(AgentRegistrationToken))).scalars().all())

    # Plaintext tokens are never stored; registration tokens are single-use.
    assert agent.token_hash == hash_token(data["agent_token"])
    assert agent.name == "nyc-1.vps"
    assert agent.last_heartbeat_at is not None
    assert registration_rows[0].used_at is not None
    assert registration_rows[0].token_hash == hash_token(minted["token"])

    audit_actions = list(
        (await session.execute(select(AuditLog.action).where(AuditLog.action == "agent.registered"))).scalars()
    )
    assert audit_actions == ["agent.registered"]


async def test_registration_token_is_single_use_and_hashed(agent_client) -> None:
    client, async_session = agent_client
    headers = auth_headers(client, "owner@example.com")

    minted = mint_registration_token(client, headers)
    first = register_agent(client, minted["token"])
    second = register_agent(client, minted["token"])

    assert first.status_code == 201
    assert second.status_code == 401

    async with async_session() as session:
        stored = (await session.execute(select(AgentRegistrationToken))).scalar_one()
    assert minted["token"] not in stored.token_hash


async def test_expired_registration_token_is_rejected(agent_client) -> None:
    client, _ = agent_client
    headers = auth_headers(client, "owner@example.com")

    minted = mint_registration_token(client, headers)
    # Expire the token directly in the DB instead of sleeping out the TTL.
    session = await app.dependency_overrides[get_db_session]().__anext__()
    row = (
        await session.execute(
            select(AgentRegistrationToken).where(
                AgentRegistrationToken.token_hash == hash_token(minted["token"])
            )
        )
    ).scalar_one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()

    result = register_agent(client, minted["token"])
    assert result.status_code == 401


async def test_heartbeat_requires_valid_agent_token(agent_client) -> None:
    client, async_session = agent_client
    headers = auth_headers(client, "owner@example.com")
    minted = mint_registration_token(client, headers)
    registered = register_agent(client, minted["token"]).json()
    agent_id = registered["agent_id"]

    no_auth = client.post(f"/api/v1/agents/{agent_id}/heartbeat", json={})
    wrong_token = client.post(
        f"/api/v1/agents/{agent_id}/heartbeat",
        json={},
        headers={"Authorization": "Bearer dck_at_not-a-real-token"},
    )
    user_token_on_agent_route = client.post(f"/api/v1/agents/{agent_id}/heartbeat", json={}, headers=headers)

    assert no_auth.status_code == 401
    assert wrong_token.status_code == 401
    assert user_token_on_agent_route.status_code == 401

    ok = client.post(
        f"/api/v1/agents/{agent_id}/heartbeat",
        json={"agent_version": "0.2.0", "metrics": {"cpu_percent": 12.5}},
        headers={"Authorization": f"Bearer {registered['agent_token']}"},
    )
    assert ok.status_code == 200
    assert ok.json()["heartbeat_interval_seconds"] == 30


async def test_agent_token_cannot_heartbeat_another_agent(agent_client) -> None:
    client, _ = agent_client
    headers = auth_headers(client, "owner@example.com")

    first = register_agent(client, mint_registration_token(client, headers)["token"]).json()
    second = register_agent(client, mint_registration_token(client, headers)["token"]).json()

    cross = client.post(
        f"/api/v1/agents/{second['agent_id']}/heartbeat",
        json={},
        headers={"Authorization": f"Bearer {first['agent_token']}"},
    )
    assert cross.status_code == 403


async def test_list_agents_derives_online_offline(agent_client) -> None:
    client, _ = agent_client
    headers = auth_headers(client, "owner@example.com")
    registered = register_agent(client, mint_registration_token(client, headers)["token"]).json()

    fresh = client.get("/api/v1/agents", headers=headers)
    assert fresh.status_code == 200
    data = fresh.json()
    assert len(data) == 1
    assert data[0]["status"] == "online"
    assert data[0]["os"] == "linux"
    assert "token_hash" not in data[0]

    # Another user must not see the agent.
    other_headers = auth_headers(client, "other@example.com")
    other_view = client.get("/api/v1/agents", headers=other_headers)
    assert other_view.json() == []

    assert registered["agent_token"] not in str(data)


async def test_rotate_token_revokes_old_token(agent_client) -> None:
    client, async_session = agent_client
    headers = auth_headers(client, "owner@example.com")
    registered = register_agent(client, mint_registration_token(client, headers)["token"]).json()
    agent_id = registered["agent_id"]

    rotated = client.post(f"/api/v1/agents/{agent_id}/rotate-token", headers=headers)
    assert rotated.status_code == 200
    new_token = rotated.json()["agent_token"]
    assert new_token != registered["agent_token"]

    old_works = client.post(f"/api/v1/agents/{agent_id}/heartbeat", json={}, headers={
        "Authorization": f"Bearer {registered['agent_token']}"
    })
    new_works = client.post(f"/api/v1/agents/{agent_id}/heartbeat", json={}, headers={
        "Authorization": f"Bearer {new_token}"
    })
    assert old_works.status_code == 401
    assert new_works.status_code == 200

    async with async_session() as session:
        actions = list(
            (await session.execute(select(AuditLog.action).where(AuditLog.action == "agent.token_rotated"))).scalars()
        )
    assert actions == ["agent.token_rotated"]
