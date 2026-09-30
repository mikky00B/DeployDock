"""Agent-driven deployments: command queue, event ingestion, dispatch (spec §15, §20, §25, §42)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session, get_sessionmaker
from app.main import app
from app.models import Agent, App, Deployment, DeploymentCommand, User
from app.models.deployment import DeploymentStatus
from app.models.deployment_command import AgentCommandStatus
from app.services.ssh_service import get_ssh_service

TEST_PRIVATE_KEY = """-----BEGIN OPENSSH PRIVATE KEY-----
test-private-key
-----END OPENSSH PRIVATE KEY-----"""


def auth_headers(client: TestClient, email: str) -> dict[str, str]:
    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "strong-password", "full_name": "Owner"},
    )
    token = register_response.json()["token"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def agent_token_headers(registered: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {registered['agent_token']}"}


@pytest.fixture
async def agent_deployment_client(monkeypatch):
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


def create_server(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/api/v1/servers",
        json={
            "name": "Agent VPS",
            "host": "203.0.113.10",
            "port": 22,
            "username": "deploy",
            "private_key": TEST_PRIVATE_KEY,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def register_agent_for_server(client: TestClient, headers: dict[str, str], server: dict) -> dict:
    minted = client.post(
        "/api/v1/agents/registration-tokens",
        json={"server_id": server["id"]},
        headers=headers,
    )
    assert minted.status_code == 201
    registered = client.post(
        "/api/v1/agents/register",
        json={"name": "nyc-1.vps", "agent_version": "0.2.0", "os": "linux", "arch": "amd64"},
        headers={"Authorization": f"Bearer {minted.json()['token']}"},
    )
    assert registered.status_code == 201
    return registered.json()


def create_app(client: TestClient, headers: dict[str, str], server: dict) -> dict:
    response = client.post(
        "/api/v1/apps",
        json={
            "name": "Watchdog",
            "server_id": server["id"],
            "repository_url": "https://github.com/example/watchdog.git",
            "branch": "main",
            "app_path": "/opt/watchdog",
            "service_name": "watchdog",
            "deploy_command": "make build",
            "restart_command": "sudo systemctl restart watchdog",
            "healthcheck_url": "/health",
            "port": 8080,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def claim_command(client: TestClient, registered: dict) -> list[dict]:
    response = client.get(
        f"/api/v1/agents/{registered['agent_id']}/commands",
        headers=agent_token_headers(registered),
    )
    assert response.status_code == 200
    return response.json()


def post_events(client: TestClient, registered: dict, deployment_id: str, events: list[dict]) -> dict:
    response = client.post(
        f"/api/v1/agents/{registered['agent_id']}/events",
        json={"events": [{"deployment_id": deployment_id, **event} for event in events]},
        headers=agent_token_headers(registered),
    )
    assert response.status_code == 200
    return response.json()


def read_deployment(client: TestClient, headers: dict[str, str], deployment_id: str) -> dict:
    response = client.get(f"/api/v1/deployments/{deployment_id}", headers=headers)
    assert response.status_code == 200
    return response.json()


async def _read_app_commits(client, app_id: str) -> tuple[str | None, str | None]:
    async with client.async_session() as session:
        row = await session.get(App, uuid.UUID(app_id))
        return row.current_commit, row.last_successful_commit


async def _read_command(client, deployment_id: str) -> DeploymentCommand:
    async with client.async_session() as session:
        return (
            await session.execute(
                select(DeploymentCommand).where(DeploymentCommand.deployment_id == uuid.UUID(deployment_id))
            )
        ).scalar_one()


def test_deploy_dispatches_to_server_agent_and_full_pipeline_succeeds(agent_deployment_client) -> None:
    client = agent_deployment_client
    headers = auth_headers(client, "owner@example.com")
    server = create_server(client, headers)
    registered = register_agent_for_server(client, headers, server)
    app_record = create_app(client, headers, server)

    deploy_response = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers)
    assert deploy_response.status_code == 202
    deployment_id = deploy_response.json()["id"]
    assert deploy_response.json()["status"] == DeploymentStatus.pending.value

    # The agent claims exactly one self-contained command.
    claimed = claim_command(client, registered)
    assert len(claimed) == 1
    command = claimed[0]
    assert command["kind"] == "deploy"
    assert command["payload"]["deployment_id"] == deployment_id
    assert command["payload"]["app"]["name"] == "Watchdog"
    assert command["payload"]["app"]["port"] == 8080
    assert command["payload"]["app"]["healthcheck_url"] == "/health"
    assert command["payload"]["app"]["container_base"] == "deploydock-watchdog"

    # A second poll claims nothing while one command is in flight.
    assert claim_command(client, registered) == []

    # The agent reports a full successful pipeline.
    result = post_events(
        client,
        registered,
        deployment_id,
        [
            {"type": "deployment_started"},
            {"type": "stage_started", "stage": "clone"},
            {"type": "stage_completed", "stage": "clone"},
            {"type": "stage_started", "stage": "build"},
            {"type": "log", "stream": "stdout", "lines": ["Step 1/4 : FROM python:3.12", "Built image"]},
            {"type": "stage_completed", "stage": "build"},
            {"type": "stage_started", "stage": "health_check"},
            {"type": "health_check_passed", "status_code": 200, "url": "http://127.0.0.1:8080/health"},
            {"type": "deployment_completed", "commit_sha": "abc123def", "duration_seconds": 41},
        ],
    )
    assert result["accepted"] == 9

    detail = read_deployment(client, headers, deployment_id)
    assert detail["status"] == DeploymentStatus.success.value
    assert detail["commit_sha"] == "abc123def"
    assert detail["healthcheck_ok"] is True
    assert detail["healthcheck_status_code"] == 200
    assert detail["finished_at"] is not None
    assert detail["duration_seconds"] == 41

    logs = client.get(f"/api/v1/deployments/{deployment_id}/logs", headers=headers).json()
    lines = [log["line"] for log in logs]
    assert "Stage started: clone" in lines
    assert "Built image" in lines
    assert "Health check passed (200)" in lines

    # Sequences are dense and ordered despite the batched insert.
    sequences = [log["sequence"] for log in logs]
    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)

    current_commit, last_successful = client.portal.start_task_soon(
        lambda: _read_app_commits(client, app_record["id"])
    ).result(timeout=10)
    assert current_commit == "abc123def"
    assert last_successful == "abc123def"

    # The agent closes the command with its claim token.
    closed = client.post(
        f"/api/v1/agents/{registered['agent_id']}/commands/{command['id']}/result",
        json={"claim_token": command["claim_token"], "succeeded": True},
        headers=agent_token_headers(registered),
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "completed"


def test_failed_pipeline_marks_deployment_failed(agent_deployment_client) -> None:
    client = agent_deployment_client
    headers = auth_headers(client, "owner@example.com")
    server = create_server(client, headers)
    registered = register_agent_for_server(client, headers, server)
    app_record = create_app(client, headers, server)

    deployment_id = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers).json()["id"]
    command = claim_command(client, registered)[0]

    post_events(
        client,
        registered,
        deployment_id,
        [
            {"type": "deployment_started"},
            {"type": "stage_started", "stage": "build"},
            {"type": "log", "stream": "stderr", "lines": ["error: docker build returned 1"]},
            {
                "type": "deployment_failed",
                "stage": "build",
                "error": "docker build failed with exit code 1",
                "duration_seconds": 12,
            },
        ],
    )

    detail = read_deployment(client, headers, deployment_id)
    assert detail["status"] == DeploymentStatus.failed.value
    assert detail["error_message"] == "docker build failed with exit code 1"
    assert detail["exit_code"] == 1

    closed = client.post(
        f"/api/v1/agents/{registered['agent_id']}/commands/{command['id']}/result",
        json={"claim_token": command["claim_token"], "succeeded": False, "error": "build failed"},
        headers=agent_token_headers(registered),
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "failed"


def test_cancel_wins_over_a_racing_agent_result(agent_deployment_client) -> None:
    client = agent_deployment_client
    headers = auth_headers(client, "owner@example.com")
    server = create_server(client, headers)
    registered = register_agent_for_server(client, headers, server)
    app_record = create_app(client, headers, server)

    deployment_id = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers).json()["id"]
    assert claim_command(client, registered)

    cancel = client.post(f"/api/v1/deployments/{deployment_id}/cancel", headers=headers)
    assert cancel.status_code == 200

    result = post_events(
        client,
        registered,
        deployment_id,
        [
            {"type": "deployment_started"},
            {"type": "deployment_completed", "commit_sha": "abc", "duration_seconds": 5},
        ],
    )
    assert result["accepted"] == 2  # delivered, but without resurrecting the row

    detail = read_deployment(client, headers, deployment_id)
    assert detail["status"] == DeploymentStatus.canceled.value


def test_events_for_deployments_the_agent_does_not_hold_are_rejected(agent_deployment_client) -> None:
    client = agent_deployment_client
    headers = auth_headers(client, "owner@example.com")
    server = create_server(client, headers)
    registered = register_agent_for_server(client, headers, server)
    # App on a different server the agent is not bound to.
    other_server = client.post(
        "/api/v1/servers",
        json={"name": "Other VPS", "host": "198.51.100.7", "port": 22, "username": "deploy", "private_key": TEST_PRIVATE_KEY},
        headers=headers,
    ).json()
    app_record = create_app(client, headers, other_server)

    async def _seed():
        async with client.async_session() as session:
            owner = (await session.execute(select(User))).scalar_one()
            deployment = Deployment(
                owner_id=owner.id,
                app_id=uuid.UUID(app_record["id"]),
                server_id=uuid.UUID(other_server["id"]),
                status=DeploymentStatus.pending,
            )
            session.add(deployment)
            await session.commit()
            return str(deployment.id)

    seeded = client.portal.start_task_soon(_seed).result(timeout=10)

    result = post_events(client, registered, seeded, [{"type": "deployment_started"}])
    assert result["accepted"] == 0
    detail = read_deployment(client, headers, seeded)
    assert detail["status"] == DeploymentStatus.pending.value


def test_result_requires_matching_claim_token(agent_deployment_client) -> None:
    client = agent_deployment_client
    headers = auth_headers(client, "owner@example.com")
    server = create_server(client, headers)
    registered = register_agent_for_server(client, headers, server)
    app_record = create_app(client, headers, server)

    deployment_id = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers).json()["id"]
    command = claim_command(client, registered)[0]

    wrong_token = client.post(
        f"/api/v1/agents/{registered['agent_id']}/commands/{command['id']}/result",
        json={"claim_token": "not-the-token", "succeeded": True},
        headers=agent_token_headers(registered),
    )
    assert wrong_token.status_code == 409

    right_token = client.post(
        f"/api/v1/agents/{registered['agent_id']}/commands/{command['id']}/result",
        json={"claim_token": command["claim_token"], "succeeded": True},
        headers=agent_token_headers(registered),
    )
    assert right_token.status_code == 200


def test_rollback_dispatches_rollback_command_with_target_commit(agent_deployment_client) -> None:
    client = agent_deployment_client
    headers = auth_headers(client, "owner@example.com")
    server = create_server(client, headers)
    registered = register_agent_for_server(client, headers, server)
    app_record = create_app(client, headers, server)

    first_id = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers).json()["id"]
    assert claim_command(client, registered)
    post_events(client, registered, first_id, [{"type": "deployment_completed", "commit_sha": "aaa111"}])

    second_id = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers).json()["id"]
    assert claim_command(client, registered)
    post_events(client, registered, second_id, [{"type": "deployment_completed", "commit_sha": "bbb222"}])

    rollback_response = client.post(f"/api/v1/deployments/{second_id}/rollback", headers=headers)
    assert rollback_response.status_code == 202
    rollback = rollback_response.json()

    command = claim_command(client, registered)[0]
    assert command["kind"] == "rollback"
    assert command["payload"]["commit_sha"] == "aaa111"  # the previous success, not bbb222


def test_server_without_agent_falls_back_to_ssh_runner(agent_deployment_client) -> None:
    client = agent_deployment_client
    headers = auth_headers(client, "owner@example.com")
    server = create_server(client, headers)  # no agent registered
    app_record = create_app(client, headers, server)

    class BoomSSH:
        async def run_command(self, **_):
            raise RuntimeError("should not be called in this assertion")

    client.app.dependency_overrides[get_ssh_service] = lambda: BoomSSH()

    deploy_response = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers)
    assert deploy_response.status_code == 202

    async def _commands() -> list[DeploymentCommand]:
        async with client.async_session() as session:
            return list((await session.execute(select(DeploymentCommand))).scalars().all())

    commands = client.portal.start_task_soon(_commands).result(timeout=10)
    assert commands == []  # no command row: the SSH bridge took it


def test_queued_deployment_is_promoted_when_active_turns_terminal(agent_deployment_client) -> None:
    """Spec §42: automatic deploys queue behind an active one and are promoted
    (back to pending) when the active deployment turns terminal."""
    client = agent_deployment_client
    headers = auth_headers(client, "owner@example.com")
    server = create_server(client, headers)
    registered = register_agent_for_server(client, headers, server)
    app_record = create_app(client, headers, server)

    first_id = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers).json()["id"]
    assert claim_command(client, registered)

    # A second deploy is created directly with queue semantics (webhook path).
    from app.services.deployment_service import create_deployment

    async def _queue_second():
        async with client.async_session() as session:
            owner = (await session.execute(select(User))).scalar_one()
            return await create_deployment(
                session,
                app_id=uuid.UUID(app_record["id"]),
                current_user=owner,
                queue_if_active=True,
            )

    queued = client.portal.start_task_soon(_queue_second).result(timeout=10)
    assert queued.status is DeploymentStatus.queued

    # The interactive path still refuses (409), unchanged.
    conflict = client.post(f"/api/v1/apps/{app_record['id']}/deploy", headers=headers)
    assert conflict.status_code == 409

    post_events(
        client,
        registered,
        first_id,
        [{"type": "deployment_completed", "commit_sha": "aaa111"}],
    )

    detail = read_deployment(client, headers, str(queued.id))
    assert detail["status"] == DeploymentStatus.pending.value

    # Promotion re-arms the queue: the agent can claim the promoted deployment.
    claimed = claim_command(client, registered)
    assert len(claimed) == 1
    assert claimed[0]["payload"]["deployment_id"] == str(queued.id)
