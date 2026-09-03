import base64

import pytest

from app.services.ssh_service import (
    HostKeyUnpinnedError,
    SSHService,
    fingerprint_host_key,
    parse_host_key,
)

RAW_KEY = b"a fake host key body"
STORED = f"ssh-ed25519 {base64.b64encode(RAW_KEY).decode()}"


def test_parse_host_key_recovers_algorithm_and_fingerprint() -> None:
    info = parse_host_key(STORED)

    assert info.algorithm == "ssh-ed25519"
    assert info.fingerprint == fingerprint_host_key(RAW_KEY)
    assert info.stored_value == STORED


def test_fingerprint_is_unpadded_sha256_base64() -> None:
    fingerprint = fingerprint_host_key(RAW_KEY)

    assert fingerprint.startswith("SHA256:")
    assert not fingerprint.endswith("=")


@pytest.mark.parametrize("value", ["", "onlyonefield", "ssh-ed25519 not-base64!!"])
def test_parse_host_key_rejects_malformed_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_host_key(value)


async def test_run_command_refuses_to_connect_without_a_pinned_host_key() -> None:
    service = SSHService()

    with pytest.raises(HostKeyUnpinnedError, match="No host key is pinned"):
        await service.run_command(
            host="203.0.113.10",
            port=22,
            username="deploy",
            private_key="unused",
            command="echo hi",
            known_host_key=None,
        )


async def test_run_command_refuses_an_empty_pinned_host_key() -> None:
    service = SSHService()

    with pytest.raises(HostKeyUnpinnedError):
        await service.run_command(
            host="203.0.113.10",
            port=22,
            username="deploy",
            private_key="unused",
            command="echo hi",
            known_host_key="",
        )
