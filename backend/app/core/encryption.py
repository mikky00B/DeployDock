import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class EncryptionError(ValueError):
    pass


def encrypt_text(value: str, encryption_key: str) -> str:
    return _get_fernet(encryption_key).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(value: str, encryption_key: str) -> str:
    try:
        decrypted = _get_fernet(encryption_key).decrypt(value.encode("ascii"))
    except InvalidToken as exc:
        raise EncryptionError("Could not decrypt value") from exc
    return decrypted.decode("utf-8")


def _get_fernet(encryption_key: str) -> Fernet:
    key_bytes = hashlib.sha256(encryption_key.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)
