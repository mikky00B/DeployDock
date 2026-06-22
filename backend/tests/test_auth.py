import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.rate_limit import login_rate_limiter
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models import User


@pytest.fixture
async def auth_client(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
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
    login_rate_limiter._attempts.clear()
    get_settings.cache_clear()
    await engine.dispose()


def test_register_creates_user_and_returns_token(auth_client) -> None:
    client, _ = auth_client

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "Owner@Example.com",
            "password": "strong-password",
            "full_name": "Deploy Owner",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["user"]["email"] == "owner@example.com"
    assert data["user"]["full_name"] == "Deploy Owner"
    assert data["token"]["token_type"] == "bearer"
    assert data["token"]["access_token"]
    assert "hashed_password" not in data["user"]


async def test_register_hashes_password(auth_client) -> None:
    _, async_session = auth_client

    async with async_session() as session:
        result = await session.execute(select(User).where(User.email == "owner@example.com"))
        user = result.scalar_one_or_none()

    assert user is None

    client, async_session = auth_client
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "owner@example.com",
            "password": "strong-password",
            "full_name": "Deploy Owner",
        },
    )

    async with async_session() as session:
        result = await session.execute(select(User).where(User.email == "owner@example.com"))
        user = result.scalar_one()

    assert user.hashed_password != "strong-password"
    assert user.hashed_password.startswith("pbkdf2_sha256$")


def test_register_rejects_duplicate_email(auth_client) -> None:
    client, _ = auth_client
    payload = {
        "email": "owner@example.com",
        "password": "strong-password",
        "full_name": "Deploy Owner",
    }

    first_response = client.post("/api/v1/auth/register", json=payload)
    second_response = client.post("/api/v1/auth/register", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Email is already registered"


def test_login_and_me(auth_client) -> None:
    client, _ = auth_client
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "owner@example.com",
            "password": "strong-password",
            "full_name": "Deploy Owner",
        },
    )

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "strong-password"},
    )
    token = login_response.json()["token"]["access_token"]
    me_response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert login_response.status_code == 200
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "owner@example.com"


def test_login_rejects_invalid_password(auth_client) -> None:
    client, _ = auth_client
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "owner@example.com",
            "password": "strong-password",
            "full_name": "Deploy Owner",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_rate_limits_repeated_invalid_passwords(auth_client) -> None:
    client, _ = auth_client
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "owner@example.com",
            "password": "strong-password",
            "full_name": "Deploy Owner",
        },
    )

    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "wrong-password"},
        )
        assert response.status_code == 401

    limited_response = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "wrong-password"},
    )

    assert limited_response.status_code == 429
    assert limited_response.json()["detail"] == "Too many failed login attempts. Try again shortly."


def test_me_rejects_unauthenticated_user(auth_client) -> None:
    client, _ = auth_client

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_register_validates_email(auth_client) -> None:
    client, _ = auth_client

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "strong-password",
            "full_name": "Deploy Owner",
        },
    )

    assert response.status_code == 422
