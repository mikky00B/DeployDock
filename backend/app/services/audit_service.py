import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User


async def create_audit_log(
    session: AsyncSession,
    *,
    current_user: User,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str,
    metadata: dict | None = None,
) -> AuditLog:
    audit_log = AuditLog(
        owner_id=current_user.id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        metadata_json=metadata,
    )
    session.add(audit_log)
    return audit_log


async def list_recent_audit_logs(
    session: AsyncSession,
    *,
    current_user: User,
    limit: int = 10,
) -> list[AuditLog]:
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.owner_id == current_user.id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
