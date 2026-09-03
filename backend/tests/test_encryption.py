import pytest

from app.core.config import Settings
from app.core.encryption import (
    EncryptionError,
    decrypt_text,
    encrypt_text,
    needs_rewrap,
    split_key_id,
)
from app.core.secrets import decrypt_secret, encrypt_secret, secret_needs_rewrap

KEY = "an-encryption-key-for-tests"
OLD_KEY = "the-previous-encryption-key"


def test_encrypt_round_trips() -> None:
    token = encrypt_text("ssh-private-key", KEY)

    assert "ssh-private-key" not in token
    assert decrypt_text(token, KEY) == "ssh-private-key"


def test_ciphertext_carries_the_key_id() -> None:
    token = encrypt_text("secret", KEY, key_id="v2")

    key_id, _ = split_key_id(token)
    assert key_id == "v2"


def test_decrypt_uses_a_retired_key_when_the_key_id_matches() -> None:
    old_token = encrypt_text("secret", OLD_KEY, key_id="v0")

    decrypted = decrypt_text(old_token, KEY, key_id="v1", retired_keys={"v0": OLD_KEY})

    assert decrypted == "secret"


def test_decrypt_reports_an_unknown_key_id() -> None:
    old_token = encrypt_text("secret", OLD_KEY, key_id="v0")

    with pytest.raises(EncryptionError, match="No encryption key available"):
        decrypt_text(old_token, KEY, key_id="v1")


def test_decrypt_rejects_a_wrong_key() -> None:
    token = encrypt_text("secret", KEY)

    with pytest.raises(EncryptionError, match="Could not decrypt"):
        decrypt_text(token, "a-completely-different-key")


def test_legacy_unprefixed_values_still_decrypt() -> None:
    import base64
    import hashlib

    from cryptography.fernet import Fernet

    fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(KEY.encode()).digest()))
    legacy_token = fernet.encrypt(b"secret").decode("ascii")

    assert split_key_id(legacy_token) == (None, legacy_token)
    assert decrypt_text(legacy_token, KEY) == "secret"


def test_needs_rewrap_flags_values_written_under_another_key_id() -> None:
    assert needs_rewrap(encrypt_text("secret", OLD_KEY, key_id="v0"), key_id="v1")
    assert not needs_rewrap(encrypt_text("secret", KEY, key_id="v1"), key_id="v1")


def test_key_id_may_not_contain_the_separator() -> None:
    with pytest.raises(EncryptionError):
        encrypt_text("secret", KEY, key_id="bad:id")


def test_settings_wrappers_apply_the_configured_key_id() -> None:
    settings = Settings(
        _env_file=None,
        ENCRYPTION_KEY=KEY,
        ENCRYPTION_KEY_ID="v2",
        ENCRYPTION_KEYS_RETIRED=f"v1:{OLD_KEY}",
    )

    token = encrypt_secret("secret", settings)
    assert split_key_id(token)[0] == "v2"
    assert decrypt_secret(token, settings) == "secret"
    assert not secret_needs_rewrap(token, settings)

    rotated_in = encrypt_text("older-secret", OLD_KEY, key_id="v1")
    assert decrypt_secret(rotated_in, settings) == "older-secret"
    assert secret_needs_rewrap(rotated_in, settings)


def test_retired_key_list_must_be_well_formed() -> None:
    with pytest.raises(ValueError, match="ENCRYPTION_KEYS_RETIRED"):
        Settings(_env_file=None, ENCRYPTION_KEYS_RETIRED="missing-separator")
