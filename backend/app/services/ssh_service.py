from dataclasses import dataclass

import asyncssh


@dataclass(frozen=True)
class SSHCommandResult:
    exit_code: int
    stdout: str
    stderr: str


class SSHService:
    async def run_command(
        self,
        *,
        host: str,
        port: int,
        username: str,
        private_key: str,
        command: str,
        timeout_seconds: int = 15,
    ) -> SSHCommandResult:
        key = asyncssh.import_private_key(private_key)
        async with asyncssh.connect(
            host,
            port=port,
            username=username,
            client_keys=[key],
            known_hosts=None,
            login_timeout=timeout_seconds,
        ) as connection:
            result = await connection.run(command, check=False, timeout=timeout_seconds)

        return SSHCommandResult(
            exit_code=result.exit_status,
            stdout=result.stdout,
            stderr=result.stderr,
        )


def get_ssh_service() -> SSHService:
    return SSHService()
