"""Email verification flow: codes, gating, resend, and notifications.

The SMTP transport is monkeypatched at the service boundary — the tests
capture what would be sent without opening a network connection.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models import EmailVerificationCode
from app.services import email_service
from app.services.email_service import _hash_code


@pytest.fixture
async def email_client(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("SMTP_HOST", "smtp.test.example")
    get_settings.cache_clear()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_get_db_session():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    sent: list[email_service.OutgoingEmail] = []

    async def fake_send(settings, email):
        sent.append(email)

    monkeypatch.setattr(email_service, "send_email", fake_send)
    with TestClient(app) as client:
        client.async_session = async_session  # type: ignore[attr-defined]
        client.sent = sent  # type: ignore[attr-defined]
        yield client

    app.dependency_overrides.clear()
    get_settings.cache_clear()
    await engine.dispose()


def register(client: TestClient, email: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "strong-password", "full_name": "Owner"},
    )
    assert response.status_code == 201
    return response.json()


async def test_register_without_verification_creates_active_account(email_client) -> None:
    """With REQUIRE_EMAIL_VERIFICATION unset, accounts are created active with
    a usable token — and no code is generated, because there is nothing to
    verify."""
    client = email_client
    data = register(client, "default@example.com")

    assert data["email_verification_required"] is False
    assert data["token"]["access_token"]
    assert data["user"]["email_verified"] is True

    async def _codes():
        async with client.async_session() as session:
            return list((await session.execute(select(EmailVerificationCode))).scalars().all())

    codes = client.portal.start_task_soon(_codes).result(timeout=10)
    assert codes == []
    assert client.sent == []


async def test_register_with_requirement_issues_code_and_empty_token(email_client, monkeypatch) -> None:
    """With REQUIRE_EMAIL_VERIFICATION=true (and SMTP configured), registering
    issues a hashed code, emails it, and returns no token."""
    client = email_client
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "true")
    get_settings.cache_clear()

    data = register(client, "code@example.com")
    assert data["email_verification_required"] is True
    assert data["token"]["access_token"] == ""
    assert data["user"]["email_verified"] is False

    async def _codes():
        async with client.async_session() as session:
            return list((await session.execute(select(EmailVerificationCode))).scalars().all())

    codes = client.portal.start_task_soon(_codes).result(timeout=10)
    assert len(codes) == 1
    assert len(client.sent) == 1
    assert client.sent[0].to == "code@example.com"
    assert "DeployDock verification code" in client.sent[0].subject


async def test_verification_gate_when_required(email_client, monkeypatch) -> None:
    """With REQUIRE_EMAIL_VERIFICATION=true, register returns no token, login
    is refused with the unverified message, and verify-email activates and
    logs the account in."""
    client = email_client
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "true")
    get_settings.cache_clear()

    data = register(client, "gated@example.com")
    assert data["email_verification_required"] is True
    assert data["token"]["access_token"] == ""
    assert data["user"]["email_verified"] is False

    # Login refused while unverified.
    refused = client.post(
        "/api/v1/auth/login",
        json={"email": "gated@example.com", "password": "strong-password"},
    )
    assert refused.status_code == 403
    assert refused.json()["detail"].startswith("Email not verified")

    # Wrong code is rejected and burns an attempt.
    wrong = client.post(
        "/api/v1/auth/verify-email",
        json={"email": "gated@example.com", "code": "000001"},
    )
    assert wrong.status_code == 400

    # The right code (from the captured email) verifies and logs in.
    code = client.sent[-1].text.split("\n\n")[2].strip()
    verified = client.post(
        "/api/v1/auth/verify-email",
        json={"email": "gated@example.com", "code": code},
    )
    assert verified.status_code == 200
    body = verified.json()
    assert body["token"]["access_token"]
    assert body["user"]["email_verified"] is True

    # Now login works.
    ok = client.post(
        "/api/v1/auth/login",
        json={"email": "gated@example.com", "password": "strong-password"},
    )
    assert ok.status_code == 200
    assert ok.json()["email_verification_required"] is False


async def test_expired_code_is_rejected(email_client, monkeypatch) -> None:
    client = email_client
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "true")
    get_settings.cache_clear()

    register(client, "expired@example.com")
    code = client.sent[-1].text.split("\n\n")[2].strip()

    async def _expire():
        async with client.async_session() as db:
            row = (await db.execute(select(EmailVerificationCode))).scalar_one()
            from datetime import UTC, datetime, timedelta

            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await db.commit()

    client.portal.start_task_soon(_expire).result(timeout=10)

    # The correct code, submitted after expiry: the hash matches but the
    # expiry check rejects it.
    response = client.post(
        "/api/v1/auth/verify-email",
        json={"email": "expired@example.com", "code": code},
    )
    assert response.status_code == 400


async def test_resend_never_reveals_registration(email_client, monkeypatch) -> None:
    client = email_client
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "true")
    get_settings.cache_clear()
    register(client, "known@example.com")
    sent_before = len(client.sent)

    # Unknown address: same 200 shape, no email.
    unknown = client.post("/api/v1/auth/resend-verification", json={"email": "ghost@example.com"})
    assert unknown.status_code == 200
    assert len(client.sent) == sent_before

    # Known address: a fresh code is issued.
    again = client.post("/api/v1/auth/resend-verification", json={"email": "known@example.com"})
    assert again.status_code == 200
    assert len(client.sent) == sent_before + 1


async def test_code_hashes_are_stored_not_plaintext(email_client, monkeypatch) -> None:
    client = email_client
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "true")
    get_settings.cache_clear()
    register(client, "hash@example.com")

    async def _read():
        async with client.async_session() as session:
            row = (await session.execute(select(EmailVerificationCode))).scalar_one()
            return row.code_hash

    stored_hash = client.portal.start_task_soon(_read).result(timeout=10)
    code = client.sent[-1].text.split("\n\n")[2].strip()
    assert stored_hash == _hash_code(code)
    assert code not in stored_hash
