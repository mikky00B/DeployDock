import base64
import hashlib
import uuid
from datetime import UTC, datetime

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.secrets import decrypt_secret, encrypt_secret
from app.models import Server, User
from app.models.server import ServerAuthType, ServerStatus
from app.schemas.server import ServerCreate, ServerUpdate
from app.services.audit_service import create_audit_log
from app.services.ssh_service import (
    HostKeyInfo,
    HostKeyMismatchError,
    HostKeyUnpinnedError,
    SSHService,
)


async def create_server(
    session: AsyncSession,
    *,
    current_user: User,
    payload: ServerCreate,
    settings: Settings,
) -> Server:
    private_key = payload.private_key
    public_key: str | None = None
    if private_key is None:
        private_key, public_key = generate_ed25519_keypair()

    server = Server(
        owner_id=current_user.id,
        name=payload.name,
        host=payload.host,
        port=payload.port,
        username=payload.username,
        auth_type=ServerAuthType.ssh_key,
        encrypted_private_key=encrypt_secret(private_key, settings),
        public_ssh_key=public_key,
        private_key_fingerprint=fingerprint_private_key(private_key),
        status=ServerStatus.unknown,
    )
    session.add(server)
    await session.flush()
    await create_audit_log(
        session,
        current_user=current_user,
        action="server.created",
        entity_type="server",
        entity_id=server.id,
        metadata={"name": server.name, "host": server.host, "generated_keypair": payload.private_key is None},
    )
    await session.commit()
    await session.refresh(server)
    return server


async def list_servers(session: AsyncSession, *, current_user: User) -> list[Server]:
    result = await session.execute(
        select(Server)
        .where(Server.owner_id == current_user.id)
        .order_by(Server.created_at.desc())
    )
    return list(result.scalars().all())


async def get_server_for_user(
    session: AsyncSession,
    *,
    server_id: uuid.UUID,
    current_user: User,
) -> Server:
    result = await session.execute(
        select(Server).where(Server.id == server_id, Server.owner_id == current_user.id)
    )
    server = result.scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    return server


async def update_server(
    session: AsyncSession,
    *,
    server: Server,
    payload: ServerUpdate,
    settings: Settings,
) -> Server:
    update_data = payload.model_dump(exclude_unset=True)
    private_key = update_data.pop("private_key", None)
    address_changed = any(
        field_name in update_data and update_data[field_name] != getattr(server, field_name)
        for field_name in ("host", "port")
    )

    for field_name, value in update_data.items():
        setattr(server, field_name, value)

    if address_changed:
        # A different host/port is a different machine as far as host key trust goes.
        server.known_host_key = None
        server.known_host_key_fingerprint = None
        server.known_host_key_pinned_at = None
        server.status = ServerStatus.unknown
        server.last_connection_check_at = None
        server.last_connection_error = None

    if private_key is not None:
        server.encrypted_private_key = encrypt_secret(private_key, settings)
        server.public_ssh_key = derive_public_key(private_key)
        server.private_key_fingerprint = fingerprint_private_key(private_key)
        server.status = ServerStatus.unknown
        server.last_connection_check_at = None
        server.last_connection_error = None

    await session.commit()
    await session.refresh(server)
    return server


async def delete_server(session: AsyncSession, *, server: Server) -> None:
    await session.delete(server)
    await session.commit()


async def test_server_connection(
    session: AsyncSession,
    *,
    server: Server,
    current_user: User,
    settings: Settings,
    ssh_service: SSHService,
) -> tuple[bool, str]:
    if server.known_host_key is None:
        # Trust on first use: pin whatever the server presents now, and surface the
        # fingerprint so the operator can compare it against the host itself.
        try:
            host_key = await ssh_service.scan_host_key(host=server.host, port=server.port)
        except Exception as exc:
            return await _record_connection_failure(
                session,
                server=server,
                current_user=current_user,
                message=f"Could not read host key from {server.host}:{server.port}: {exc}",
            )
        pin_host_key(server, host_key)

    private_key = decrypt_secret(server.encrypted_private_key, settings)

    try:
        result = await ssh_service.run_command(
            host=server.host,
            port=server.port,
            username=server.username,
            private_key=private_key,
            command="echo deploydock-ok",
            known_host_key=server.known_host_key,
        )
    except (HostKeyMismatchError, HostKeyUnpinnedError) as exc:
        return await _record_connection_failure(
            session,
            server=server,
            current_user=current_user,
            message=str(exc),
        )
    except Exception as exc:
        return await _record_connection_failure(
            session,
            server=server,
            current_user=current_user,
            message=f"SSH connection failed: {exc}",
        )

    success = result.exit_code == 0 and "deploydock-ok" in result.stdout
    server.status = ServerStatus.connected if success else ServerStatus.unreachable
    server.last_connection_error = None if success else result.stderr or "Connection test command failed"
    server.last_connection_check_at = datetime.now(UTC)
    await create_audit_log(
        session,
        current_user=current_user,
        action="server.connection_tested",
        entity_type="server",
        entity_id=server.id,
        metadata={"success": success, "status": server.status.value},
    )
    await session.commit()
    await session.refresh(server)

    if success:
        return True, "SSH connection succeeded"
    return False, server.last_connection_error or "SSH connection failed"


def fingerprint_private_key(private_key: str) -> str:
    digest = hashlib.sha256(private_key.encode("utf-8")).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def generate_ed25519_keypair() -> tuple[str, str]:
    private_key = ed25519.Ed25519PrivateKey.generate()
    private_text = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_text = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("utf-8")
    return private_text, public_text


def derive_public_key(private_key_text: str) -> str | None:
    try:
        private_key = serialization.load_ssh_private_key(private_key_text.encode("utf-8"), password=None)
    except ValueError:
        return None
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("utf-8")


def pin_host_key(server: Server, host_key: HostKeyInfo) -> None:
    server.known_host_key = host_key.stored_value
    server.known_host_key_fingerprint = host_key.fingerprint
    server.known_host_key_pinned_at = datetime.now(UTC)


async def repin_server_host_key(
    session: AsyncSession,
    *,
    server: Server,
    current_user: User,
    ssh_service: SSHService,
) -> tuple[HostKeyInfo, str | None]:
    """Replace the pinned host key with the one the server presents now.

    Returns the newly pinned key and the fingerprint it replaced, so the caller can
    show the operator exactly what changed. This is a deliberate, explicit action:
    a mismatch is either a rebuilt server or an attack, and only the operator knows which.
    """
    previous_fingerprint = server.known_host_key_fingerprint
    host_key = await ssh_service.scan_host_key(host=server.host, port=server.port)
    pin_host_key(server, host_key)
    server.status = ServerStatus.unknown
    server.last_connection_error = None
    await create_audit_log(
        session,
        current_user=current_user,
        action="server.host_key_pinned",
        entity_type="server",
        entity_id=server.id,
        metadata={
            "fingerprint": host_key.fingerprint,
            "previous_fingerprint": previous_fingerprint,
        },
    )
    await session.commit()
    await session.refresh(server)
    return host_key, previous_fingerprint


async def _record_connection_failure(
    session: AsyncSession,
    *,
    server: Server,
    current_user: User,
    message: str,
) -> tuple[bool, str]:
    server.status = ServerStatus.unreachable
    server.last_connection_error = message
    server.last_connection_check_at = datetime.now(UTC)
    await create_audit_log(
        session,
        current_user=current_user,
        action="server.connection_tested",
        entity_type="server",
        entity_id=server.id,
        metadata={"success": False, "status": server.status.value},
    )
    await session.commit()
    await session.refresh(server)
    return False, message
