from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core import rate_limit
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models import User
from app.schemas.auth import AuthUserResponse, LoginRequest, LogoutResponse, RegisterRequest, TokenResponse
from app.schemas.user import UserRead
from app.services.auth_service import authenticate_user, create_user_access_token, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


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
    )
    access_token = create_user_access_token(user, settings)
    return AuthUserResponse(
        user=UserRead.model_validate(user),
        token=TokenResponse(access_token=access_token),
    )


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
    access_token = create_user_access_token(user, settings)
    return AuthUserResponse(
        user=UserRead.model_validate(user),
        token=TokenResponse(access_token=access_token),
    )


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
