"""Email delivery: signup verification codes and deployment notifications.

Delivery is stdlib smtplib run in a worker thread (no new dependency, and the
event loop never blocks on SMTP). Two graceful-degradation rules:

- With `SMTP_HOST` unset, email is disabled entirely: verification codes are
  not sent and accounts are created already verified (unless
  `REQUIRE_EMAIL_VERIFICATION` demands otherwise), and deployment
  notifications are dropped.
- Email failures never fail the operation that triggered them — a deploy that
  succeeded must still be success even if the SMTP server is down.
"""

import asyncio
import hashlib
import logging
import secrets
import smtplib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import EmailVerificationCode, User

logger = logging.getLogger("deploydock.email")

CODE_PURPOSE_SIGNUP = "signup"


@dataclass
class OutgoingEmail:
    to: str
    subject: str
    text: str
    html: str


def _deliver_sync(settings: Settings, email: OutgoingEmail) -> None:
    message = EmailMessage()
    message["Subject"] = email.subject
    message["From"] = (
        f"{settings.email_from_name} <{settings.email_from}>"
        if settings.email_from_name
        else settings.email_from
    )
    message["To"] = email.to
    message.set_content(email.text)
    message.add_alternative(email.html, subtype="html")

    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)


async def send_email(settings: Settings, email: OutgoingEmail) -> None:
    """Send one email without ever raising. Returns after the SMTP round-trip."""
    if not settings.smtp_host:
        logger.debug("Email disabled (SMTP_HOST unset); dropping %r to %s", email.subject, email.to)
        return
    try:
        await asyncio.to_thread(_deliver_sync, settings, email)
        logger.info("Email sent: %r -> %s", email.subject, email.to)
    except Exception:
        logger.exception("Email delivery failed: %r -> %s", email.subject, email.to)


def email_enabled(settings: Settings) -> bool:
    return bool(settings.smtp_host)


# ---- verification codes ----

def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def issue_verification_code(
    session: AsyncSession,
    *,
    user: User,
    settings: Settings,
) -> str | None:
    """Create and email a fresh signup code. Returns the plaintext code, or
    None when email is disabled (or sending failed).

    Issuing a new code consumes every previous unconsumed one, so "the newest
    code" is always the only live code — no timestamp-ordering dependency when
    two codes land within the same clock tick.
    """
    code = generate_code()
    await session.execute(
        update(EmailVerificationCode)
        .where(
            EmailVerificationCode.user_id == user.id,
            EmailVerificationCode.consumed_at.is_(None),
        )
        .values(consumed_at=datetime.now(UTC))
    )
    session.add(
        EmailVerificationCode(
            user_id=user.id,
            code_hash=_hash_code(code),
            purpose=CODE_PURPOSE_SIGNUP,
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.email_code_ttl_seconds),
        )
    )
    await session.commit()
    await send_email(settings, render_verification_email(user, code, settings))
    return code if email_enabled(settings) else None


async def consume_verification_code(
    session: AsyncSession,
    *,
    user: User,
    code: str,
    settings: Settings,
) -> bool:
    """Verify and consume the user's newest signup code.

    Every wrong attempt counts against the newest code only; after
    `email_code_max_attempts` wrong tries it is burned and a new one must be
    requested.
    """
    result = await session.execute(
        select(EmailVerificationCode)
        .where(
            EmailVerificationCode.user_id == user.id,
            EmailVerificationCode.purpose == CODE_PURPOSE_SIGNUP,
            EmailVerificationCode.consumed_at.is_(None),
        )
        .order_by(EmailVerificationCode.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return False

    if _hash_code(code.strip()) != record.code_hash:
        record.attempts += 1
        burned = record.attempts >= settings.email_code_max_attempts
        if burned:
            record.consumed_at = datetime.now(UTC)
        await session.commit()
        logger.info("Wrong verification code for user %s (attempt %s)", user.id, record.attempts)
        return False

    now = datetime.now(UTC)
    if _as_utc(record.expires_at) < now:
        record.consumed_at = now
        await session.commit()
        return False

    record.consumed_at = now
    user.email_verified = True
    user.email_verified_at = now
    await session.commit()
    # The commit expires the server-onupdate `updated_at`; refresh so the
    # caller's sync serialization (Pydantic) cannot trigger a lazy load.
    await session.refresh(user)
    return True


def render_verification_email(user: User, code: str, settings: Settings) -> OutgoingEmail:
    name = user.full_name or user.email.split("@")[0]
    text = (
        f"Hi {name},\n\n"
        f"Your DeployDock verification code is:\n\n{code}\n\n"
        f"It expires in {settings.email_code_ttl_seconds // 60} minutes. "
        "If you didn't create a DeployDock account, you can ignore this email.\n\n"
        "— DeployDock"
    )
    html = (
        '<html><body style="font-family:Segoe UI,Arial,sans-serif;'
        'color:#e6edf3;background:#0d1117;padding:32px">\n'
        '  <h2 style="margin:0 0 16px">Verify your DeployDock account</h2>\n'
        f"  <p>Hi {name}, your verification code is:</p>\n"
        '  <p style="font-size:32px;letter-spacing:8px;font-family:monospace;'
        f'color:#58a6ff;margin:16px 0"><b>{code}</b></p>\n'
        f"  <p style=\"color:#8b949e\">It expires in "
        f"{settings.email_code_ttl_seconds // 60} minutes.\n"
        "  If you didn't create a DeployDock account, you can ignore this email.</p>\n"
        "</body></html>"
    )
    subject = f"{code} is your DeployDock verification code"
    return OutgoingEmail(to=user.email, subject=subject, text=text, html=html)


# ---- deployment notifications ----

def render_deployment_result_email(
    *,
    app_name: str,
    status: str,
    commit_sha: str | None,
    duration_seconds: int | None,
    error_message: str | None,
    settings: Settings,
) -> OutgoingEmail:
    succeeded = status == "success"
    subject = f"{'✓' if succeeded else '✗'} DeployDock: {app_name} deployment {status}"
    commit_line = f"Commit: {commit_sha}\n" if commit_sha else ""
    error_line = f"\nError:\n{error_message}\n" if error_message else ""
    duration_line = f"Duration: {duration_seconds}s\n" if duration_seconds is not None else ""
    dashboard = settings.app_public_url.rstrip("/")
    text = (
        f"Your deployment of {app_name} {status}.\n\n"
        f"{commit_line}{duration_line}{error_line}\n"
        f"Details: {dashboard}/deployments\n\n— DeployDock"
    )
    color = "#2ea043" if succeeded else "#f85149"
    error_block = (
        '<pre style="color:#f85149;background:#161b22;padding:12px;'
        f'border-radius:6px">{error_message}</pre>'
        if error_message
        else ""
    )
    html = (
        '<html><body style="font-family:Segoe UI,Arial,sans-serif;'
        'color:#e6edf3;background:#0d1117;padding:32px">\n'
        f'  <h2 style="margin:0 0 8px">Deployment <span style="color:{color}">{status}</span></h2>\n'
        f'  <p style="margin:0 0 16px"><b>{app_name}</b></p>\n'
        f"  <p style=\"color:#8b949e\">{commit_line.replace(chr(10), '<br>')}"
        f"{duration_line.replace(chr(10), '<br>')}</p>\n"
        f"  {error_block}\n"
        f'  <p><a href="{dashboard}/deployments" style="color:#58a6ff">Open deployment history</a></p>\n'
        "</body></html>"
    )
    return OutgoingEmail(to="", subject=subject, text=text, html=html)


async def notify_deployment_result(session: AsyncSession, *, deployment_id) -> None:
    """Email the owner when their deployment reaches success or failure.

    Best-effort by design: called from deployment terminal paths, it must
    never delay or break the deployment bookkeeping. Runs the SMTP round-trip
    in a detached thread via send_email's to_thread.
    """
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.smtp_host or not settings.email_notifications_enabled:
        return

    from app.models import App, Deployment

    deployment = await session.get(Deployment, deployment_id)
    if deployment is None or deployment.status not in ("success", "failed"):
        return
    owner = await session.get(User, deployment.owner_id)
    if owner is None or not owner.email_verified:
        return
    app = await session.get(App, deployment.app_id)
    app_name = app.name if app else "your app"

    email = render_deployment_result_email(
        app_name=app_name,
        status=deployment.status.value if hasattr(deployment.status, "value") else str(deployment.status),
        commit_sha=deployment.commit_sha,
        duration_seconds=deployment.duration_seconds,
        error_message=deployment.error_message,
        settings=settings,
    )
    email.to = owner.email
    # Fire-and-forget with a held reference: deployment bookkeeping has
    # already committed, so this must not block or break it.
    task = asyncio.create_task(send_email(settings, email))
    _notification_tasks.add(task)
    task.add_done_callback(_notification_tasks.discard)


_notification_tasks: set[asyncio.Task] = set()


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
