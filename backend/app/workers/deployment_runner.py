import shlex
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.encryption import decrypt_text
from app.models import App, Deployment, DeploymentLog, Server
from app.models.deployment import DeploymentStatus
from app.models.deployment_log import DeploymentLogStream
from app.services.audit_service import create_audit_log
from app.services.ssh_service import SSHCommandResult, SSHService


class DeploymentRunner:
    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        settings: Settings,
        ssh_service: SSHService,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.settings = settings
        self.ssh_service = ssh_service

    async def run(self, deployment_id: uuid.UUID) -> None:
        async with self.sessionmaker() as session:
            deployment = await self._get_deployment(session, deployment_id)
            app = deployment.app
            server = deployment.server
            started_at = datetime.now(UTC)

            deployment.status = DeploymentStatus.running
            deployment.started_at = started_at
            await self._add_log(session, deployment, DeploymentLogStream.system, "Deployment started")
            await session.commit()

            private_key = decrypt_text(server.encrypted_private_key, self.settings.encryption_key)

            try:
                previous_commit = await self._read_current_commit(server, app, private_key)
                deployment.previous_commit_sha = previous_commit
                if previous_commit:
                    await self._add_log(
                        session,
                        deployment,
                        DeploymentLogStream.system,
                        f"Previous commit: {previous_commit}",
                    )

                result = await self.ssh_service.run_command(
                    host=server.host,
                    port=server.port,
                    username=server.username,
                    private_key=private_key,
                    command=build_deploy_command(app.app_path, app.deploy_command),
                    timeout_seconds=900,
                )
                await self._save_command_output(session, deployment, result)

                deployment.exit_code = result.exit_code
                if result.exit_code == 0:
                    deployment.status = DeploymentStatus.success
                    deployment.commit_sha = await self._read_current_commit(server, app, private_key)
                    app.current_commit = deployment.commit_sha
                    app.last_successful_commit = deployment.commit_sha
                    await self._add_log(session, deployment, DeploymentLogStream.system, "Deployment succeeded")
                    await create_audit_log(
                        session,
                        current_user=deployment.owner,
                        action="deployment.succeeded",
                        entity_type="deployment",
                        entity_id=deployment.id,
                        metadata={"app_id": str(app.id), "commit_sha": deployment.commit_sha},
                    )
                else:
                    deployment.status = DeploymentStatus.failed
                    deployment.error_message = result.stderr.strip() or "Deployment command failed"
                    await self._add_log(session, deployment, DeploymentLogStream.system, "Deployment failed")
                    await create_audit_log(
                        session,
                        current_user=deployment.owner,
                        action="deployment.failed",
                        entity_type="deployment",
                        entity_id=deployment.id,
                        metadata={"app_id": str(app.id), "exit_code": result.exit_code},
                    )
            except Exception as exc:
                deployment.status = DeploymentStatus.failed
                deployment.error_message = f"Deployment failed: {exc}"
                await self._add_log(session, deployment, DeploymentLogStream.system, deployment.error_message)
                await create_audit_log(
                    session,
                    current_user=deployment.owner,
                    action="deployment.failed",
                    entity_type="deployment",
                    entity_id=deployment.id,
                    metadata={"app_id": str(app.id), "error": str(exc)},
                )
            finally:
                finished_at = datetime.now(UTC)
                deployment.finished_at = finished_at
                deployment.duration_seconds = max(0, int((finished_at - started_at).total_seconds()))
                await session.commit()

    async def run_rollback(self, deployment_id: uuid.UUID) -> None:
        async with self.sessionmaker() as session:
            deployment = await self._get_deployment(session, deployment_id)
            app = deployment.app
            server = deployment.server
            target_commit = deployment.commit_sha
            started_at = datetime.now(UTC)

            deployment.status = DeploymentStatus.running
            deployment.started_at = started_at
            await self._add_log(session, deployment, DeploymentLogStream.system, "Rollback started")
            await session.commit()

            if target_commit is None:
                deployment.status = DeploymentStatus.failed
                deployment.error_message = "Rollback target commit is missing"
                deployment.finished_at = datetime.now(UTC)
                deployment.duration_seconds = 0
                await self._add_log(session, deployment, DeploymentLogStream.system, deployment.error_message)
                await session.commit()
                return

            private_key = decrypt_text(server.encrypted_private_key, self.settings.encryption_key)

            try:
                result = await self.ssh_service.run_command(
                    host=server.host,
                    port=server.port,
                    username=server.username,
                    private_key=private_key,
                    command=build_rollback_command(app, target_commit),
                    timeout_seconds=300,
                )
                await self._save_command_output(session, deployment, result)

                deployment.exit_code = result.exit_code
                if result.exit_code == 0:
                    deployment.status = DeploymentStatus.success
                    deployment.commit_sha = target_commit
                    app.current_commit = target_commit
                    await self._add_log(session, deployment, DeploymentLogStream.system, "Rollback succeeded")
                else:
                    deployment.status = DeploymentStatus.failed
                    deployment.error_message = result.stderr.strip() or "Rollback command failed"
                    await self._add_log(session, deployment, DeploymentLogStream.system, "Rollback failed")
            except Exception as exc:
                deployment.status = DeploymentStatus.failed
                deployment.error_message = f"Rollback failed: {exc}"
                await self._add_log(session, deployment, DeploymentLogStream.system, deployment.error_message)
            finally:
                finished_at = datetime.now(UTC)
                deployment.finished_at = finished_at
                deployment.duration_seconds = max(0, int((finished_at - started_at).total_seconds()))
                await session.commit()

    async def _get_deployment(self, session: AsyncSession, deployment_id: uuid.UUID) -> Deployment:
        result = await session.execute(
            select(Deployment)
            .options(
                selectinload(Deployment.app),
                selectinload(Deployment.owner),
                selectinload(Deployment.server),
                selectinload(Deployment.logs),
            )
            .where(Deployment.id == deployment_id)
        )
        deployment = result.scalar_one()
        return deployment

    async def _read_current_commit(self, server: Server, app: App, private_key: str) -> str | None:
        result = await self.ssh_service.run_command(
            host=server.host,
            port=server.port,
            username=server.username,
            private_key=private_key,
            command=build_git_commit_command(app.app_path),
            timeout_seconds=30,
        )
        if result.exit_code != 0:
            return None
        commit = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
        return commit[:64] if commit else None

    async def _save_command_output(
        self,
        session: AsyncSession,
        deployment: Deployment,
        result: SSHCommandResult,
    ) -> None:
        for line in result.stdout.splitlines():
            await self._add_log(session, deployment, DeploymentLogStream.stdout, line)
        for line in result.stderr.splitlines():
            await self._add_log(session, deployment, DeploymentLogStream.stderr, line)

    async def _add_log(
        self,
        session: AsyncSession,
        deployment: Deployment,
        stream: DeploymentLogStream,
        line: str,
    ) -> None:
        sequence = len(deployment.logs) + 1
        log = DeploymentLog(
            deployment_id=deployment.id,
            stream=stream,
            line=line,
            sequence=sequence,
        )
        deployment.logs.append(log)
        session.add(log)


def build_git_commit_command(app_path: str) -> str:
    return f"cd {shlex.quote(app_path)} && git rev-parse HEAD"


def build_deploy_command(app_path: str, deploy_command: str) -> str:
    script = f"set -e\ncd {shlex.quote(app_path)}\n{deploy_command}"
    return "bash -lc " + shlex.quote(script)


def build_rollback_command(app: App, target_commit: str) -> str:
    restart_command = app.restart_command
    if restart_command is None and app.service_name:
        restart_command = f"sudo systemctl restart {shlex.quote(app.service_name)}"

    script_lines = [
        "set -e",
        f"cd {shlex.quote(app.app_path)}",
        "git fetch",
        f"git checkout {shlex.quote(target_commit)}",
    ]
    if restart_command:
        script_lines.append(restart_command)

    return "bash -lc " + shlex.quote("\n".join(script_lines))
