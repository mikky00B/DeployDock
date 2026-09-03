"""Password hashing and access tokens.

Passwords are hashed with Argon2id. Hashes written by the previous
pbkdf2_sha256 implementation are still verified, and `needs_rehash` tells
callers when to transparently upgrade one on a successful login.

Tokens are signed JWTs (HS256) produced by PyJWT. Every token carries `iat`,
`nbf`, `exp` and a `jti`, and decoding pins the accepted algorithm so a token
cannot claim a weaker one.
"""

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

LEGACY_HASH_ALGORITHM = "pbkdf2_sha256"
JWT_ALGORITHM = "HS256"

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    if stored_hash.startswith(f"{LEGACY_HASH_ALGORITHM}$"):
        return _verify_legacy_password(password, stored_hash)

    try:
        return _password_hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    """True when a stored hash should be replaced on the next successful login."""
    if stored_hash.startswith(f"{LEGACY_HASH_ALGORITHM}$"):
        return True
    try:
        return _password_hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


def create_access_token(
    *,
    subject: str,
    secret_key: str,
    expires_delta: timedelta,
) -> str:
    issued_at = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": int(issued_at.timestamp()),
        "nbf": int(issued_at.timestamp()),
        "exp": int((issued_at + expires_delta).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, *, secret_key: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(
            token,
            secret_key,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None


def _verify_legacy_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected_hash = stored_hash.split("$", 3)
        iterations = int(iterations_text)
    except ValueError:
        return False

    if algorithm != LEGACY_HASH_ALGORITHM:
        return False

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return hmac.compare_digest(password_hash.hex(), expected_hash)
