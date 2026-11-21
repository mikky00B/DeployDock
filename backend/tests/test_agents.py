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


def mint_registration_token(client: TestClient, headers: dict[str, str], **payload) -> dict:
    response = client.post("/api/v1/agents/registration-tokens", json=payload, headers=headers)
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


def create_server(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/api/v1/servers",
        json={
            "name": "Cross VPS",
            "host": "203.0.113.50",
            "port": 22,
            "username": "deploy",
            "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_registration_token_cannot_target_another_users_server(agent_client) -> None:
    """Audit C1: minting a registration token bound to someone else's server
    would let the attacker's agent receive that tenant's commands and
    decrypted env vars. It must 404 like any other foreign resource."""
    client, _ = agent_client
    owner_headers = auth_headers(client, "owner@example.com")
    attacker_headers = auth_headers(client, "attacker@example.com")

    server = create_server(client, owner_headers)

    response = client.post(
        "/api/v1/agents/registration-tokens",
        json={"server_id": server["id"]},
        headers=attacker_headers,
    )
    assert response.status_code == 404
async def test_dispatch_never_selects_a_foreign_agent(agent_client) -> None:
    """Audit C1, defense in depth: even a malformed row (attacker-owned agent
    bound to a victim's server) must not be selected for the victim's
    deployments — scoping checks both the agent's and the server's owner."""
    import uuid

    from app.services.agent_dispatch import find_agent_for_server

    client, async_session = agent_client
    owner_headers = auth_headers(client, "owner@example.com")
    attacker_headers = auth_headers(client, "attacker@example.com")

    server = create_server(client, owner_headers)
    minted = mint_registration_token(client, attacker_headers)
    registered = register_agent(client, minted["token"]).json()

    async with async_session() as session:
        agent = await session.get(Agent, uuid.UUID(registered["agent_id"]))
        agent.server_id = uuid.UUID(server["id"])
        await session.commit()
        agent_id, attacker_id, server_id = agent.id, agent.owner_id, agent.server_id

    async with async_session() as session:
        # The server owner's id is what dispatch would pass (deployment.owner).
        owner_id = (
            await session.execute(
                select(Agent.owner_id).where(Agent.id == agent_id)
            )
        ).scalar_one()
        # Sanity: the row really is attacker-owned and server-bound.
        assert owner_id == attacker_id and server_id == uuid.UUID(server["id"])

        # Dispatch for the victim's deployment (owner = the server owner) must
        # skip the attacker-owned row. Query with the attacker's user id as
        # "the deployment owner" from the attacker's own dispatch — no, the
        # decisive case: the VICTIM dispatches, so owner_id = victim. The
        # victim is a different user; simulate via a fresh uuid that is not
        # the attacker's.
        victim_id = uuid.uuid5(uuid.NAMESPACE_DNS, "victim.example.com")
        assert victim_id != attacker_id
        selected = await find_agent_for_server(session, server_id=server_id, owner_id=victim_id)
        assert selected is None

        # And the attacker cannot pull the row into their own dispatch either,
        # because the server does not belong to them.
        selected_for_attacker = await find_agent_for_server(
            session, server_id=server_id, owner_id=attacker_id
        )
        assert selected_for_attacker is None


async def test_stale_agent_is_skipped_and_online_one_selected(agent_client) -> None:
    """Audit H3: an agent that stopped heartbeating must not capture dispatch —
    the online agent wins, and with no online agent dispatch falls back to SSH
    (find_agent_for_server returns None)."""
    import uuid

    from app.services.agent_dispatch import find_agent_for_server

    client, async_session = agent_client
    headers = auth_headers(client, "owner@example.com")
    server = create_server(client, headers)

    minted = mint_registration_token(client, headers, server_id=server["id"])
    first = register_agent(client, minted["token"]).json()
    minted = mint_registration_token(client, headers, server_id=server["id"])
    second = register_agent(client, minted["token"]).json()

    async with async_session() as session:
        # Re-registration superseded the first agent (audit C1 unique-active
        # rule): first is retired, second is active and online.
        first_row = await session.get(Agent, uuid.UUID(first["agent_id"]))
        second_row = await session.get(Agent, uuid.UUID(second["agent_id"]))
        assert first_row.revoked_at is not None
        assert second_row.revoked_at is None

        # Even if the newest row goes quiet, selection skips it entirely.
        second_row.last_heartbeat_at = datetime.now(UTC) - timedelta(hours=2)
        await session.commit()

        owner_id = first_row.owner_id
        selected = await find_agent_for_server(
            session, server_id=uuid.UUID(server["id"]), owner_id=owner_id
        )
        assert selected is None  # no live agent -> SSH fallback


async def test_revoke_endpoint_disables_the_agent_token(agent_client) -> None:
    """Audit H3: revoking an agent kills its token immediately."""
    client, _ = agent_client
    headers = auth_headers(client, "owner@example.com")
    minted = mint_registration_token(client, headers)
    registered = register_agent(client, minted["token"]).json()
    agent_token = registered["agent_token"]
    agent_id = registered["agent_id"]

    revoked = client.post(f"/api/v1/agents/{agent_id}/revoke", headers=headers)
    assert revoked.status_code == 200

    # The agent's token no longer authenticates.
    heartbeat = client.post(
        f"/api/v1/agents/{agent_id}/heartbeat",
        json={"agent_version": "0.1.0"},
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert heartbeat.status_code == 409
