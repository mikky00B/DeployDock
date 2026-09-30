import json
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db_session, get_sessionmaker
from app.models import User, WebhookDeliveryResult
from app.schemas.deployment import DeploymentRead
from app.services.agent_dispatch import dispatch_deployment
from app.services.app_service import get_app_for_user
from app.services.webhook_service import (
    delivery_already_processed,
    extract_commit_sha,
    extract_push_info,
    find_candidate_apps,
    handle_push,
    record_delivery,
    verify_signature,
    webhook_owner_for_app,
)
from app.services.ssh_service import SSHService, get_ssh_service
from app.workers.deployment_runner import DeploymentRunner

import secrets

from app.core.encryption import encrypt_text

router = APIRouter(tags=["webhooks"])


@router.post("/apps/{app_id}/webhook-secret", status_code=status.HTTP_201_CREATED)
async def create_webhook_secret(
    app_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    """Mint the app's GitHub webhook secret (shown once, encrypted at rest)."""
    app = await get_app_for_user(session, app_id=app_id, current_user=current_user)
    secret = "whsec_" + secrets.token_urlsafe(32)
    app.encrypted_webhook_secret = encrypt_text(
        secret, settings.encryption_key, key_id=settings.encryption_key_id
    )
    await session.commit()
    return {"webhook_secret": secret, "header": "X-Hub-Signature-256"}


@router.post("/webhooks/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    sessionmaker: Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)],
    settings: Annotated[Settings, Depends(get_settings)],
    ssh_service: Annotated[SSHService, Depends(get_ssh_service)],
    x_github_event: Annotated[str | None, Header()] = None,
    x_github_delivery: Annotated[str | None, Header()] = None,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
) -> dict:
    """Receive GitHub events (spec §40). Always answers 202 while logging the
    outcome, so GitHub does not retry storms on rejected deliveries."""
    raw_body = await request.body()
    delivery_id = x_github_delivery or f"missing-{uuid.uuid4().hex[:12]}"
    event = x_github_event or "unknown"

    if await delivery_already_processed(session, delivery_id=delivery_id):
        return {"webhook_result": "ignored", "reason": "delivery already processed"}

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        await record_delivery(
            session,
            app_id=None,
            delivery_id=delivery_id,
            event=event,
            action=None,
            result=WebhookDeliveryResult.rejected,
            detail="invalid JSON",
        )
        return {"webhook_result": "rejected", "reason": "invalid JSON"}

    if event == "ping":
        await record_delivery(
            session,
            app_id=None,
            delivery_id=delivery_id,
            event=event,
            action=None,
            result=WebhookDeliveryResult.ignored,
            detail="ping acknowledged",
        )
        return {"webhook_result": "ignored", "reason": "ping"}

    full_name, branch, head_message = extract_push_info(payload)
    if not full_name or not branch:
        await record_delivery(
            session,
            app_id=None,
            delivery_id=delivery_id,
            event=event,
            action=None,
            result=WebhookDeliveryResult.ignored,
            detail="not a push event with repository/branch",
        )
        return {"webhook_result": "ignored", "reason": "unsupported event"}

    candidates = await find_candidate_apps(session, full_name=full_name)
    branch_match = [app for app in candidates if app.branch == branch]
    if not branch_match:
        await record_delivery(
            session,
            app_id=None,
            delivery_id=delivery_id,
            event=event,
            action="push",
            result=WebhookDeliveryResult.ignored,
            detail=f"no auto-deploy app for {full_name}@{branch}",
        )
        return {"webhook_result": "ignored", "reason": "no matching app"}

    # Signature verification against each candidate's decrypted secret.
    verified_app = None
    for app in branch_match:
        if not app.encrypted_webhook_secret:
            continue
        from app.core.encryption import decrypt_text

        try:
            secret = decrypt_text(
                app.encrypted_webhook_secret,
                settings.encryption_key,
                key_id=settings.encryption_key_id,
                retired_keys=settings.retired_encryption_keys,
            )
        except Exception:  # noqa: BLE001 - undecryptable secret = unverifiable app
            continue
        if verify_signature(secret=secret, signature_header=x_hub_signature_256, raw_body=raw_body):
            verified_app = app
            break

    if verified_app is None:
        await record_delivery(
            session,
            app_id=branch_match[0].id,
            delivery_id=delivery_id,
            event=event,
            action="push",
            result=WebhookDeliveryResult.rejected,
            detail="signature verification failed",
        )
        return {"webhook_result": "rejected", "reason": "signature verification failed"}

    commit_sha = extract_commit_sha(payload)
    owner = await webhook_owner_for_app(session, app=verified_app)
    deployment = await handle_push(
        session,
        app=verified_app,
        commit_message=head_message,
        commit_sha=commit_sha,
        current_user=owner,
        settings=settings,
    )
    if deployment.status.value == "pending":
        dispatched = await dispatch_deployment(session, deployment=deployment)
        if not dispatched:
            runner = DeploymentRunner(sessionmaker=sessionmaker, settings=settings, ssh_service=ssh_service)
            background_tasks.add_task(runner.run, deployment.id)
    # Queued deployments wait: promotion paths dispatch them later (spec §42).

    result = (
        WebhookDeliveryResult.queued
        if deployment.status.value == "queued"
        else WebhookDeliveryResult.deployed
    )
    await record_delivery(
        session,
        app_id=verified_app.id,
        delivery_id=delivery_id,
        event=event,
        action="push",
        result=result,
        detail=f"deployment {deployment.id}",
    )
    return DeploymentRead.model_validate(deployment).model_dump(mode="json") | {"webhook_result": result.value}
