import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any


HASH_ALGORITHM = "pbkdf2_sha256"
HASH_ITERATIONS = 260_000
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        HASH_ITERATIONS,
    )
    return f"{HASH_ALGORITHM}${HASH_ITERATIONS}${salt}${password_hash.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected_hash = stored_hash.split("$", 3)
        iterations = int(iterations_text)
    except ValueError:
        return False

    if algorithm != HASH_ALGORITHM:
        return False

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return hmac.compare_digest(password_hash.hex(), expected_hash)


def create_access_token(
    *,
    subject: str,
    secret_key: str,
    expires_delta: timedelta,
) -> str:
    expires_at = datetime.now(UTC) + expires_delta
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload = {"sub": subject, "exp": int(expires_at.timestamp())}

    signing_input = ".".join(
        [
            _base64url_encode_json(header),
            _base64url_encode_json(payload),
        ]
    )
    signature = _sign(signing_input, secret_key)
    return f"{signing_input}.{signature}"


def decode_access_token(token: str, *, secret_key: str) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None

    signing_input = ".".join(parts[:2])
    expected_signature = _sign(signing_input, secret_key)
    if not hmac.compare_digest(expected_signature, parts[2]):
        return None

    payload = _base64url_decode_json(parts[1])
    if payload is None:
        return None

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < int(datetime.now(UTC).timestamp()):
        return None

    return payload


def _sign(signing_input: str, secret_key: str) -> str:
    signature = hmac.new(
        secret_key.encode("utf-8"),
        signing_input.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _base64url_encode(signature)


def _base64url_encode_json(value: dict[str, Any]) -> str:
    json_bytes = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _base64url_encode(json_bytes)


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode_json(value: str) -> dict[str, Any] | None:
    padding = "=" * (-len(value) % 4)
    try:
        raw = base64.urlsafe_b64decode(f"{value}{padding}")
        decoded = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None

    if not isinstance(decoded, dict):
        return None
    return decoded
