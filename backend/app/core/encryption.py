"""Symmetric encryption for secrets at rest (SSH private keys).

Ciphertext is stored with a key-id prefix so the encryption key can be rotated
without a manual, all-or-nothing re-encrypt:

    v1:gAAAAAB...

`ENCRYPTION_KEY` supplies the active key. `ENCRYPTION_KEYS_RETIRED` may hold
previously active keys (comma-separated `id:secret` pairs) which are still
accepted for decryption. Values written before key ids existed are stored
without a prefix and are decrypted with the legacy key derivation.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

KEY_ID_SEPARATOR = ":"
LEGACY_KEY_ID = "legacy"


class EncryptionError(ValueError):
    pass


def encrypt_text(value: str, encryption_key: str, *, key_id: str = "v1") -> str:
    if KEY_ID_SEPARATOR in key_id:
        raise EncryptionError(f"Key id must not contain {KEY_ID_SEPARATOR!r}")
    token = _get_fernet(encryption_key).encrypt(value.encode("utf-8")).decode("ascii")
    return f"{key_id}{KEY_ID_SEPARATOR}{token}"


def decrypt_text(
    value: str,
    encryption_key: str,
    *,
    key_id: str = "v1",
    retired_keys: dict[str, str] | None = None,
) -> str:
    stored_key_id, token = split_key_id(value)

    if stored_key_id is None:
        # Written before key ids were introduced: only the active key can open it.
        candidates = [encryption_key]
    elif stored_key_id == key_id:
        candidates = [encryption_key]
    elif retired_keys and stored_key_id in retired_keys:
        candidates = [retired_keys[stored_key_id]]
    else:
        raise EncryptionError(
            f"No encryption key available for key id {stored_key_id!r}. "
            "Add it to ENCRYPTION_KEYS_RETIRED to decrypt values written with it."
        )

    for candidate in candidates:
        try:
            return _get_fernet(candidate).decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken:
            continue

    raise EncryptionError("Could not decrypt value")


def split_key_id(value: str) -> tuple[str | None, str]:
    """Split a stored value into (key_id, token). key_id is None for legacy values."""
    head, separator, tail = value.partition(KEY_ID_SEPARATOR)
    if not separator or not head or head.startswith("gAAAAA"):
        return None, value
    return head, tail


def needs_rewrap(value: str, *, key_id: str = "v1") -> bool:
    """True when the value is not encrypted under the currently active key id."""
    stored_key_id, _ = split_key_id(value)
    return stored_key_id != key_id


def _get_fernet(encryption_key: str) -> Fernet:
    key_bytes = hashlib.sha256(encryption_key.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)
