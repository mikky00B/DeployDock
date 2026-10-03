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
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import App, Deployment, WebhookDelivery, WebhookDeliveryResult


def verify_signature(*, secret: str, signature_header: str | None, raw_body: bytes) -> bool:
    """Constant-time verification of 'sha256=<hex>' against the raw body."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=").strip().lower()
    return hmac.compare_digest(expected, provided)


async def find_candidate_apps(session: AsyncSession, *, full_name: str) -> list[App]:
    """Apps whose repository_url references this GitHub repo."""
    needle = full_name.lower()
    result = await session.execute(select(App).where(App.auto_deploy.is_(True)))
    apps = list(result.scalars().all())
    candidates = []
    for app in apps:
        url = (app.repository_url or "").lower()
        # Accept github.com/<owner>/<name> in any common suffix shape.
        if needle in url:
            candidates.append(app)
    return candidates


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
) -> None:
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
    await session.commit()


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
