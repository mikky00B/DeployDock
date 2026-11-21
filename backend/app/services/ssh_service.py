import base64
import hashlib
import shlex
import uuid
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
        env: dict[str, str] | None = None,
    ) -> SSHCommandResult:
        """Run a command over SSH, verifying the server's host key.

        `known_host_key` is the pinned '<algorithm> <base64>' value from the server
        row. It is required: connecting without verification would expose the
        decrypted private key to a man-in-the-middle.

        `env`, when given, is delivered as a 0600 env file uploaded over SFTP and
        sourced inside the remote shell — never as part of the command string,
        which would land the values in the remote host's process list and shell
        audit logs (audit H1). The file is removed by the command itself.
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
                if env:
                    # Remote path on the managed host; the uuid suffix makes it
                    # unguessable and it is removed by the command itself.
                    env_path = f"/tmp/deploydock-env-{uuid.uuid4().hex}.sh"  # noqa: S108
                    body = "".join(
                        f"export {shlex.quote(key_)}={shlex.quote(value)}\n"
                        for key_, value in env.items()
                    )
                    async with connection.start_sftp() as sftp:
                        async with sftp.open(env_path, "w") as env_file:
                            await env_file.write(body)
                        await sftp.chmod(env_path, 0o600)
                    command = (
                        f"set -a\n. {shlex.quote(env_path)}\nset +a\n"
                        f"{command}\nrm -f {shlex.quote(env_path)}"
                    )
                result = await connection.run(command, check=False, timeout=timeout_seconds)
        except asyncssh.HostKeyNotVerifiable as exc:
            raise HostKeyMismatchError(
                f"Host key for {host}:{port} does not match the pinned key "
                f"({expected.fingerprint}). Refusing to connect. If you rebuilt or "
                "replaced this server, re-pin its host key from the server page."
            ) from exc

        # asyncssh >= 2.19 widened these types: stdout/stderr can be None (or
        # bytes in binary mode), and exit_status is None when the server sent
        # no exit status at all (e.g. the channel closed early) - treat that as
        # a failure rather than a silent success.
        return SSHCommandResult(
            exit_code=result.exit_status if result.exit_status is not None else 1,
            stdout=result.stdout if isinstance(result.stdout, str) else "",
            stderr=result.stderr if isinstance(result.stderr, str) else "",
        )


def get_ssh_service() -> SSHService:
    return SSHService()
