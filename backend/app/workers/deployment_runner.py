import asyncio
import shlex
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.secrets import decrypt_secret
from app.models import App, Deployment, DeploymentLog, Server
from app.models.deployment import TERMINAL_DEPLOYMENT_STATUSES, DeploymentStatus
from app.models.deployment_log import DeploymentLogStream
from app.services.audit_service import create_audit_log
from app.services.deployment_events import deployment_event_bus
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
        # Monotonic log line counter for the deployment currently being run.
        # A single runner owns a deployment end to end, so a local counter is both
        # correct and O(1) - unlike len(deployment.logs), which was O(n) per line.
        self._sequence = 0

    async def run(self, deployment_id: uuid.UUID) -> None:
        self._sequence = 0
        async with self.sessionmaker() as session:
            deployment = await self._get_deployment(session, deployment_id)
            app = deployment.app
            server = deployment.server
            started_at = datetime.now(UTC)

            # Cancel checkpoint: the row may have been canceled while the
            # background task sat in the queue.
            await self._refresh_status(session, deployment)
            if self._is_canceled(deployment):
                await self._add_log(
                    session,
                    deployment,
                    DeploymentLogStream.system,
                    "Deployment canceled before start",
                )
                await session.commit()
                return

            deployment.status = DeploymentStatus.running
            deployment.started_at = started_at
            await self._add_log(session, deployment, DeploymentLogStream.system, "Deployment started")
            await session.commit()
            deployment_event_bus.notify(deployment.id)

            private_key = decrypt_secret(server.encrypted_private_key, self.settings)

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
                    known_host_key=server.known_host_key,
                    timeout_seconds=self.settings.deploy_timeout_seconds,
                )
                await self._save_command_output(session, deployment, result)
                await session.commit()
                deployment_event_bus.notify(deployment.id)

                deployment.exit_code = result.exit_code
                # Cancel checkpoint: the SSH bridge cannot abort a command that
                # is already executing, so a cancel that lands mid-run is
                # honoured here, after the current command has returned.
                await self._refresh_status(session, deployment)
                if self._is_canceled(deployment):
                    deployment.exit_code = None
                    await self._add_log(
                        session,
                        deployment,
                        DeploymentLogStream.system,
                        "Deployment canceled; ignoring the result of the command that was already running",
                    )
                    await create_audit_log(
                        session,
                        current_user=deployment.owner,
                        action="deployment.canceled",
                        entity_type="deployment",
                        entity_id=deployment.id,
                        metadata={"app_id": str(app.id), "note": "honored after command returned"},
                    )
                elif result.exit_code == 0:
                    deployment.status = DeploymentStatus.success
                    deployment.commit_sha = await self._read_current_commit(server, app, private_key)
                    app.current_commit = deployment.commit_sha
                    app.last_successful_commit = deployment.commit_sha
                    await self._add_log(
                        session, deployment, DeploymentLogStream.system, "Deployment succeeded"
                    )
                    await create_audit_log(
                        session,
                        current_user=deployment.owner,
                        action="deployment.succeeded",
                        entity_type="deployment",
                        entity_id=deployment.id,
                        metadata={"app_id": str(app.id), "commit_sha": deployment.commit_sha},
                    )
                else:
                    # A cancel already stamped the terminal status; never
                    # overwrite it with "failed" here.
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
                # Never overwrite a terminal status the API already stamped
                # (e.g. a cancel that landed while the command was running).
                await self._refresh_status(session, deployment)
                if deployment.status not in TERMINAL_DEPLOYMENT_STATUSES:
                    deployment.status = DeploymentStatus.failed
                    deployment.error_message = f"Deployment failed: {exc}"
                    await self._add_log(
                        session,
                        deployment,
                        DeploymentLogStream.system,
                        deployment.error_message,
                    )
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
                deployment_event_bus.notify(deployment.id)
                await self._promote_next_queued(session, deployment)

    async def run_rollback(self, deployment_id: uuid.UUID) -> None:
        self._sequence = 0
        async with self.sessionmaker() as session:
            deployment = await self._get_deployment(session, deployment_id)
            app = deployment.app
            server = deployment.server
            target_commit = deployment.commit_sha
            started_at = datetime.now(UTC)

            # Cancel checkpoint: the row may have been canceled while the
            # background task sat in the queue.
            await self._refresh_status(session, deployment)
            if self._is_canceled(deployment):
                await self._add_log(
                    session,
                    deployment,
                    DeploymentLogStream.system,
                    "Rollback canceled before start",
                )
                await session.commit()
                return

            deployment.status = DeploymentStatus.running
            deployment.started_at = started_at
            await self._add_log(session, deployment, DeploymentLogStream.system, "Rollback started")
            await session.commit()
            deployment_event_bus.notify(deployment.id)

            if target_commit is None:
                deployment.status = DeploymentStatus.failed
                deployment.error_message = "Rollback target commit is missing"
                deployment.finished_at = datetime.now(UTC)
                deployment.duration_seconds = 0
                await self._add_log(session, deployment, DeploymentLogStream.system, deployment.error_message)
                await session.commit()
                return

            private_key = decrypt_secret(server.encrypted_private_key, self.settings)

            try:
                result = await self.ssh_service.run_command(
                    host=server.host,
                    port=server.port,
                    username=server.username,
                    private_key=private_key,
                    command=build_rollback_command(app, target_commit),
                    known_host_key=server.known_host_key,
                    timeout_seconds=self.settings.rollback_timeout_seconds,
                )
                await self._save_command_output(session, deployment, result)
                await session.commit()
                deployment_event_bus.notify(deployment.id)

                deployment.exit_code = result.exit_code
                await self._refresh_status(session, deployment)
                if self._is_canceled(deployment):
                    deployment.exit_code = None
                    await self._add_log(
                        session,
                        deployment,
                        DeploymentLogStream.system,
                        "Rollback canceled; ignoring the result of the command that was already running",
                    )
                elif result.exit_code == 0:
                    deployment.status = DeploymentStatus.success
                    deployment.commit_sha = target_commit
                    app.current_commit = target_commit
                    await self._add_log(session, deployment, DeploymentLogStream.system, "Rollback succeeded")
                else:
                    deployment.status = DeploymentStatus.failed
                    deployment.error_message = result.stderr.strip() or "Rollback command failed"
                    await self._add_log(session, deployment, DeploymentLogStream.system, "Rollback failed")
            except Exception as exc:
                # Never overwrite a terminal status the API already stamped
                # (e.g. a cancel that landed while the command was running).
                await self._refresh_status(session, deployment)
                if deployment.status not in TERMINAL_DEPLOYMENT_STATUSES:
                    deployment.status = DeploymentStatus.failed
                    deployment.error_message = f"Rollback failed: {exc}"
                    await self._add_log(
                        session,
                        deployment,
                        DeploymentLogStream.system,
                        deployment.error_message,
                    )
            finally:
                finished_at = datetime.now(UTC)
                deployment.finished_at = finished_at
                deployment.duration_seconds = max(0, int((finished_at - started_at).total_seconds()))
                await session.commit()
                deployment_event_bus.notify(deployment.id)
                await self._promote_next_queued(session, deployment)

    async def _promote_next_queued(self, session: AsyncSession, deployment: Deployment) -> None:
        """Promote (spec §42) and dispatch whatever queued behind this deploy.

        Runs after the terminal commit: the promoted deployment either goes to
        the server's agent as a command, or — on agent-less servers — back
        through this SSH runner as a follow-up task.
        """
        from app.services.agent_dispatch import (
            dispatch_deployment,
            promote_next_queued_deployment,
        )

        try:
            promoted = await promote_next_queued_deployment(session, app_id=deployment.app_id)
        except Exception:  # noqa: BLE001 - promotion must never fail the deploy
            return
        if promoted is None:
            return
        try:
            dispatched = await dispatch_deployment(session, deployment=promoted)
        except Exception:  # noqa: BLE001
            dispatched = False
        if not dispatched:
            asyncio.create_task(self.run(promoted.id))

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

    async def _refresh_status(self, session: AsyncSession, deployment: Deployment) -> None:
        """Re-read the committed status onto the tracked row.

        Cancellation happens in a different transaction (the API request), so
        the runner's in-memory copy goes stale; every checkpoint must look at
        the database, not at its own last write.
        """
        await session.refresh(deployment, attribute_names=["status"])

    def _is_canceled(self, deployment: Deployment) -> bool:
        """True when the deployment row was canceled after creation.

        Strict on purpose: the checkpoints only react to an actual cancel so
        their log lines tell the truth, while the exception paths use the
        broader terminal-status guard so they never overwrite a status the API
        has already stamped.
        """
        return deployment.status is DeploymentStatus.canceled

    async def _read_current_commit(self, server: Server, app: App, private_key: str) -> str | None:
        result = await self.ssh_service.run_command(
            host=server.host,
            port=server.port,
            username=server.username,
            private_key=private_key,
            command=build_git_commit_command(app.app_path),
            known_host_key=server.known_host_key,
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
        self._sequence += 1
        sequence = self._sequence
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
