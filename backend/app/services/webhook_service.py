"""GitHub webhook handling (spec §40-41).

Security model:
- signature verification: X-Hub-Signature-256 (HMAC-SHA256 over the raw body)
  checked with hmac.compare_digest against each candidate app's decrypted
  secret — a request is only trusted when a candidate verifies;
- replay protection: X-GitHub-Delivery ids are recorded; repeats are answered
  without side effects;
- repository and branch validation: only push events for the app's repository
  and branch, with auto_deploy enabled, trigger a deployment.
"""

import hashlib
import hmac
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import App, Deployment, WebhookDelivery, WebhookDeliveryResult

# Audit M1: an unauthenticated endpoint must not buffer unbounded bodies.
MAX_WEBHOOK_BODY_BYTES = 1 * 1024 * 1024


def verify_signature(*, secret: str, signature_header: str | None, raw_body: bytes) -> bool:
    """Constant-time verification of 'sha256=<hex>' against the raw body."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=").strip().lower()
    return hmac.compare_digest(expected, provided)


def github_full_name(repository_url: str | None) -> str | None:
    """The 'owner/name' a repository URL refers to, or None.

    Exact matching (audit M1): a substring test made `github.com/a/b` match
    every URL containing `a/b`, cross-tenant. Parsing to owner/name matches
    only the repository the URL actually points at.
    """
    from urllib.parse import urlsplit

    if not repository_url:
        return None
    parts = [segment for segment in urlsplit(repository_url).path.split("/") if segment]
    if len(parts) < 2:
        return None
    name = parts[-1].removesuffix(".git")
    return f"{parts[-2]}/{name}".lower()


async def find_candidate_apps(session: AsyncSession, *, full_name: str) -> list[App]:
    """Apps whose repository URL resolves to exactly this GitHub repo."""
    target = full_name.lower()
    result = await session.execute(select(App).where(App.auto_deploy.is_(True)))
    apps = list(result.scalars().all())
    return [app for app in apps if github_full_name(app.repository_url) == target]


async def delivery_already_processed(session: AsyncSession, *, delivery_id: str) -> bool:
    result = await session.execute(
        select(WebhookDelivery.id).where(WebhookDelivery.delivery_id == delivery_id).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def record_delivery(
    session: AsyncSession,
    *,
    app_id: uuid.UUID | None,
    delivery_id: str,
    event: str,
    action: str | None,
    result: WebhookDeliveryResult,
    detail: str | None = None,
) -> bool:
    """Persist the delivery outcome. False when a concurrent request recorded
    the same delivery id first — the database settles the replay race."""
    session.add(
        WebhookDelivery(
            app_id=app_id,
            delivery_id=delivery_id,
            event=event,
            action=action,
            result=result,
            detail=detail,
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        # A concurrent request recorded this delivery id first; its outcome
        # stands and this one is a duplicate.
        await session.rollback()
        return False
    return True


def extract_push_info(payload: dict) -> tuple[str | None, str | None, str | None]:
    """(full_name, branch, head_message) from a push event payload."""
    repository = payload.get("repository") or {}
    full_name = repository.get("full_name")
    ref = payload.get("ref") or ""
    branch = ref.removeprefix("refs/heads/") if ref.startswith("refs/heads/") else None
    head = payload.get("head_commit") or {}
    message = head.get("message")
    return full_name, branch, message


def extract_commit_sha(payload: dict) -> str | None:
    after = payload.get("after")
    if isinstance(after, str) and after and set(after) != {"0"}:
        return after
    return None


async def handle_push(
    session: AsyncSession,
    *,
    app: App,
    commit_message: str | None,
    commit_sha: str | None,
    current_user,
) -> Deployment:
    """A verified push for this app: create (or queue) the deployment.

    The local import keeps deployment_service → app_service → server_service
    out of this module's import cycle; deployment_service does not import
    webhook_service, so this is one-directional at call time.
    """
    from app.services.deployment_service import create_deployment

    deployment = await create_deployment(
        session,
        app_id=app.id,
        current_user=current_user,
        queue_if_active=True,
        commit_message=commit_message,
    )
    deployment.commit_sha = commit_sha
    deployment.triggered_by = "github-webhook"
    await session.commit()
    await session.refresh(deployment)
    return deployment


async def webhook_owner_for_app(session: AsyncSession, *, app: App):
    from app.models import User

    return await session.get(User, app.owner_id)
