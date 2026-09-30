from fastapi import APIRouter

from app.api.v1 import agents, apps, auth, dashboard, deployments, environments, servers, webhooks

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(servers.router)
api_router.include_router(apps.router)
api_router.include_router(deployments.router)
api_router.include_router(agents.router)
api_router.include_router(environments.router)
api_router.include_router(webhooks.router)
