"""Prometheus /metrics endpoint (spec §48)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app


@pytest.fixture
async def metrics_client(monkeypatch):
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

    # /metrics reads through the app-global sessionmaker, not the dependency.
    import app.main as main_module

    monkeypatch.setattr(main_module, "AsyncSessionLocal", async_session)
    app.dependency_overrides[get_db_session] = override_get_db_session

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    get_settings.cache_clear()
    await engine.dispose()


def test_metrics_endpoint_renders_prometheus_text(metrics_client: TestClient) -> None:
    response = metrics_client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text

    # Core metric families from spec §48.
    assert "# HELP deployment_total" in body
    assert 'deployment_total{status="pending"}' in body
    assert "deployment_duration_seconds_sum" in body
    assert "deployment_duration_seconds_count" in body
    assert "servers_total" in body
    assert "apps_total" in body
    assert "agents_online" in body
    assert "agents_total" in body

    # Every pipeline status renders a line, so dashboards can't regress silently.
    for status_value in (
        "queued", "cloning", "building", "testing", "deploying",
        "health_check", "running", "success", "failed", "canceled", "rolled_back",
    ):
        assert f'status="{status_value}"' in body
