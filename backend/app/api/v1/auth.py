from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core import rate_limit
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models import User
from app.schemas.auth import (
    AuthUserResponse,
    LoginRequest,
    LogoutResponse,
    RegisterRequest,
    ResendVerificationRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.schemas.user import UserRead
from app.services import email_service
from app.services.auth_service import (
    authenticate_user,
    create_user_access_token,
    get_user_by_email,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_UNVERIFIED_DETAIL = (
    "Email not verified. Enter the 6-digit code we emailed you, or request a new one."
)


def _auth_response(user: User, settings: Settings) -> AuthUserResponse:
    """A logged-in response, or a verification-required response when the
    account has not confirmed its emailed code yet."""
    must_verify = settings.require_email_verification and not user.email_verified
    access_token = "" if must_verify else create_user_access_token(user, settings)
    return AuthUserResponse(
        user=UserRead.model_validate(user),
        token=TokenResponse(access_token=access_token),
        email_verification_required=must_verify,
    )


@router.post(
    "/register",
    response_model=AuthUserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: Request,
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthUserResponse:
    # Registration is unauthenticated, so every attempt counts against the
    # source address — not only failures (there is no credential to fail).
    throttle_keys = [f"reg-ip:{rate_limit.client_ip(request, settings)}"]
    await rate_limit.register_rate_limiter.check(throttle_keys)
    await rate_limit.register_rate_limiter.record_failure(throttle_keys)

    user = await register_user(
        session,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        settings=settings,
    )
    return _auth_response(user, settings)


@router.post("/verify-email", response_model=AuthUserResponse)
async def verify_email(
    payload: VerifyEmailRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthUserResponse:
    """Confirm the emailed 6-digit code. On success the client is logged in."""
    user = await get_user_by_email(session, payload.email.lower())
    if user is None or user.email_verified:
        # No user enumeration: an unknown (or already verified) address gets
        # the same rejection as a wrong code.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )
    verified = await email_service.consume_verification_code(
        session, user=user, code=payload.code, settings=settings
    )
    if not verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )
    return _auth_response(user, settings)


@router.post("/resend-verification")
async def resend_verification(
    payload: ResendVerificationRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    """Re-issue the signup code. Always `200` — the response must not reveal
    whether the address is registered."""
    user = await get_user_by_email(session, payload.email.lower())
    if user is not None and not user.email_verified and email_service.email_enabled(settings):
        await email_service.issue_verification_code(session, user=user, settings=settings)
    return {"detail": "If the address needs verification, a new code has been sent."}


@router.post("/login", response_model=AuthUserResponse)
async def login(
    request: Request,
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthUserResponse:
    rate_limit_keys = build_login_rate_limit_keys(request, payload.email, settings)
    await rate_limit.login_rate_limiter.check(rate_limit_keys)
    user = await authenticate_user(session, email=payload.email, password=payload.password)
    if user is None:
        await rate_limit.login_rate_limiter.record_failure(rate_limit_keys)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await rate_limit.login_rate_limiter.reset(rate_limit_keys)

    if settings.require_email_verification and not user.email_verified:
        # Correct credentials, unconfirmed address: ask for the code. A fresh
        # code goes out so the user is never stuck without one.
        await email_service.issue_verification_code(session, user=user, settings=settings)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=EMAIL_UNVERIFIED_DETAIL,
        )

    return _auth_response(user, settings)


@router.post("/logout", response_model=LogoutResponse)
async def logout() -> LogoutResponse:
    return LogoutResponse(detail="Logged out")


@router.get("/me", response_model=UserRead)
async def me(current_user: Annotated[User, Depends(get_current_user)]) -> UserRead:
    return UserRead.model_validate(current_user)


def build_login_rate_limit_keys(request: Request, email: str, settings: Settings) -> list[str]:
    """Limit per source IP, per account, and per pair.

    Limiting only on IP+email lets an attacker walk a list of emails from one IP,
    or one email from many IPs, without ever tripping the limit.
    """
    client_host = rate_limit.client_ip(request, settings)
    normalized_email = email.lower()
    return [
        f"ip:{client_host}",
        f"email:{normalized_email}",
        f"pair:{client_host}:{normalized_email}",
    ]
