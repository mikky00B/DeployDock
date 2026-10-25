import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key")
# Hard-set (not setdefault): Settings also reads backend/.env, so a developer's
# local REQUIRE_EMAIL_VERIFICATION=true or SMTP_HOST must not leak into the
# suite. Tests that exercise email set their own values in their fixtures.
os.environ["REQUIRE_EMAIL_VERIFICATION"] = "false"
os.environ["SMTP_HOST"] = ""

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
