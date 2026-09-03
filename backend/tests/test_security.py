import hashlib
import secrets
from datetime import timedelta

import jwt
import pytest

from app.core.security import (
    JWT_ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    needs_rehash,
    verify_password,
)

SECRET = "a-test-secret-key-that-is-long-enough-for-hs256"


def test_hash_password_uses_argon2_and_verifies() -> None:
    hashed = hash_password("strong-password")

    assert hashed.startswith("$argon2")
    assert verify_password("strong-password", hashed)
    assert not verify_password("wrong-password", hashed)


def test_hash_password_salts_each_hash() -> None:
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_password_accepts_legacy_pbkdf2_hashes() -> None:
    salt = secrets.token_hex(16)
    iterations = 260_000
    digest = hashlib.pbkdf2_hmac("sha256", b"legacy-password", salt.encode(), iterations).hex()
    legacy_hash = f"pbkdf2_sha256${iterations}${salt}${digest}"

    assert verify_password("legacy-password", legacy_hash)
    assert not verify_password("other-password", legacy_hash)
    assert needs_rehash(legacy_hash)


def test_needs_rehash_is_false_for_a_current_hash() -> None:
    assert not needs_rehash(hash_password("strong-password"))


def test_needs_rehash_is_true_for_garbage() -> None:
    assert needs_rehash("not-a-hash")


def test_access_token_round_trips_with_standard_claims() -> None:
    token = create_access_token(
        subject="user-123",
        secret_key=SECRET,
        expires_delta=timedelta(minutes=30),
    )
    payload = decode_access_token(token, secret_key=SECRET)

    assert payload is not None
    assert payload["sub"] == "user-123"
    assert {"iat", "nbf", "exp", "jti"} <= payload.keys()


def test_access_token_jti_is_unique_per_token() -> None:
    first = decode_access_token(
        create_access_token(subject="u", secret_key=SECRET, expires_delta=timedelta(minutes=5)),
        secret_key=SECRET,
    )
    second = decode_access_token(
        create_access_token(subject="u", secret_key=SECRET, expires_delta=timedelta(minutes=5)),
        secret_key=SECRET,
    )

    assert first is not None and second is not None
    assert first["jti"] != second["jti"]


def test_decode_rejects_a_token_signed_with_another_key() -> None:
    token = create_access_token(subject="u", secret_key=SECRET, expires_delta=timedelta(minutes=5))

    assert decode_access_token(token, secret_key="a-different-secret-key-entirely!!") is None


def test_decode_rejects_expired_tokens() -> None:
    token = create_access_token(subject="u", secret_key=SECRET, expires_delta=timedelta(minutes=-1))

    assert decode_access_token(token, secret_key=SECRET) is None


def test_decode_rejects_the_none_algorithm() -> None:
    forged = jwt.encode({"sub": "u", "exp": 9_999_999_999}, key="", algorithm="none")

    assert decode_access_token(forged, secret_key=SECRET) is None


def test_decode_rejects_tokens_missing_required_claims() -> None:
    no_sub = jwt.encode({"exp": 9_999_999_999}, SECRET, algorithm=JWT_ALGORITHM)

    assert decode_access_token(no_sub, secret_key=SECRET) is None


@pytest.mark.parametrize("token", ["", "not.a.token", "a.b", "a.b.c.d"])
def test_decode_rejects_malformed_tokens(token: str) -> None:
    assert decode_access_token(token, secret_key=SECRET) is None
