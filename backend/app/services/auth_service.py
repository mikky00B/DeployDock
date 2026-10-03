from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import create_access_token, hash_password, needs_rehash, verify_password
from app.models import User


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str | None,
    settings: Settings,
) -> User:
    """Create an account.

    When `REQUIRE_EMAIL_VERIFICATION` is on (and SMTP is configured), the
    account starts unverified and a 6-digit code is emailed; login is refused
    until the code is confirmed. Otherwise the account is created active —
    local development and tests work with no SMTP server.
    """
    from app.services import email_service

    normalized_email = email.lower()
    existing_user = await get_user_by_email(session, normalized_email)
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    must_verify = settings.require_email_verification and email_service.email_enabled(settings)
    user = User(
        email=normalized_email,
        hashed_password=hash_password(password),
        full_name=full_name,
        email_verified=not must_verify,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    if must_verify:
        await email_service.issue_verification_code(session, user=user, settings=settings)
    return user


async def authenticate_user(session: AsyncSession, *, email: str, password: str) -> User | None:
    user = await get_user_by_email(session, email.lower())
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None

    # Transparently upgrade hashes written by an older algorithm or weaker parameters.
    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(password)
        await session.commit()
        await session.refresh(user)

    return user


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


def create_user_access_token(user: User, settings: Settings) -> str:
    return create_access_token(
        subject=str(user.id),
        secret_key=settings.secret_key,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
