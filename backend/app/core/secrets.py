"""Settings-aware wrappers around the encryption primitives.

Callers should use these rather than `app.core.encryption` directly so the
active key id and the retired-key set are applied consistently everywhere.
"""

from app.core.config import Settings
from app.core.encryption import decrypt_text, encrypt_text, needs_rewrap


def encrypt_secret(value: str, settings: Settings) -> str:
    return encrypt_text(value, settings.encryption_key, key_id=settings.encryption_key_id)


def decrypt_secret(value: str, settings: Settings) -> str:
    return decrypt_text(
        value,
        settings.encryption_key,
        key_id=settings.encryption_key_id,
        retired_keys=settings.retired_encryption_keys,
    )


def secret_needs_rewrap(value: str, settings: Settings) -> bool:
    return needs_rewrap(value, key_id=settings.encryption_key_id)
