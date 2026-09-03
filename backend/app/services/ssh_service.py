import base64
import hashlib
from dataclasses import dataclass

import asyncssh


class HostKeyMismatchError(Exception):
    """Raised when a server presents a host key that does not match the pinned one."""


class HostKeyUnpinnedError(Exception):
    """Raised when a connection is attempted before a host key has been pinned."""


@dataclass(frozen=True)
class SSHCommandResult:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class HostKeyInfo:
    """A server host key, in the form we persist and show to the user."""

    algorithm: str
    base64_key: str
    fingerprint: str

    @property
    def stored_value(self) -> str:
        """Serialized form stored on the server row: '<algorithm> <base64>'."""
        return f"{self.algorithm} {self.base64_key}"


def fingerprint_host_key(key_bytes: bytes) -> str:
    digest = hashlib.sha256(key_bytes).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def parse_host_key(stored_value: str) -> HostKeyInfo:
    """Parse a stored '<algorithm> <base64>' host key back into HostKeyInfo."""
    parts = stored_value.strip().split()
    if len(parts) < 2:
        raise ValueError("Stored host key is malformed")
    algorithm, base64_key = parts[0], parts[1]
    try:
        key_bytes = base64.b64decode(base64_key, validate=True)
    except Exception as exc:  # noqa: BLE001 - normalize to ValueError for callers
        raise ValueError("Stored host key is not valid base64") from exc
    return HostKeyInfo(
        algorithm=algorithm,
        base64_key=base64_key,
        fingerprint=fingerprint_host_key(key_bytes),
    )


def host_key_info_from_key(key: asyncssh.SSHKey) -> HostKeyInfo:
    key_bytes = key.public_data
    return HostKeyInfo(
        algorithm=key.get_algorithm(),
        base64_key=base64.b64encode(key_bytes).decode("ascii"),
        fingerprint=fingerprint_host_key(key_bytes),
    )


class SSHService:
    async def scan_host_key(
        self,
        *,
        host: str,
        port: int,
        timeout_seconds: int = 15,
    ) -> HostKeyInfo:
        """Fetch the host key a server currently presents, without authenticating.

        Used during onboarding so the user can review the fingerprint before it is
        pinned. This step is inherently trust-on-first-use; every later connection
        verifies against the pinned value.
        """
        key = await asyncssh.get_server_host_key(host, port)
        if key is None:
            raise ConnectionError(f"{host}:{port} did not present a host key")
        return host_key_info_from_key(key)

    async def run_command(
        self,
        *,
        host: str,
        port: int,
        username: str,
        private_key: str,
        command: str,
        known_host_key: str | None,
        timeout_seconds: int = 15,
    ) -> SSHCommandResult:
        """Run a command over SSH, verifying the server's host key.

        `known_host_key` is the pinned '<algorithm> <base64>' value from the server
        row. It is required: connecting without verification would expose the
        decrypted private key to a man-in-the-middle.
        """
        if not known_host_key:
            raise HostKeyUnpinnedError(
                "No host key is pinned for this server. Run a connection test to "
                "review and accept the server's host key first."
            )

        expected = parse_host_key(known_host_key)
        key = asyncssh.import_private_key(private_key)

        try:
            async with asyncssh.connect(
                host,
                port=port,
                username=username,
                client_keys=[key],
                known_hosts=([asyncssh.import_public_key(expected.stored_value)], [], []),
                login_timeout=timeout_seconds,
            ) as connection:
                result = await connection.run(command, check=False, timeout=timeout_seconds)
        except asyncssh.HostKeyNotVerifiable as exc:
            raise HostKeyMismatchError(
                f"Host key for {host}:{port} does not match the pinned key "
                f"({expected.fingerprint}). Refusing to connect. If you rebuilt or "
                "replaced this server, re-pin its host key from the server page."
            ) from exc

        return SSHCommandResult(
            exit_code=result.exit_status,
            stdout=result.stdout,
            stderr=result.stderr,
        )


def get_ssh_service() -> SSHService:
    return SSHService()
