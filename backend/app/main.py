import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.rate_limit import configure_login_rate_limiter
from app.db.session import AsyncSessionLocal, engine
from app.services.deployment_service import fail_orphaned_deployments

settings = get_settings()
configure_logging(settings.app_env)
logger = logging.getLogger("deploydock")


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_login_rate_limiter(settings)

    # Deployments run in-process, so anything left pending/running belongs to a
    # process that is no longer alive. Reclaim those rows, otherwise the
    # one-active-deployment-per-app guard would block the app forever.
    try:
        async with AsyncSessionLocal() as session:
            reclaimed = await fail_orphaned_deployments(
                session,
                older_than_seconds=settings.orphan_deployment_timeout_seconds,
            )
        if reclaimed:
            logger.warning("Marked %s interrupted deployment(s) as failed at startup", reclaimed)
    except Exception:  # noqa: BLE001 - never block startup on the sweep
        logger.exception("Could not sweep interrupted deployments at startup")

    yield


app = FastAPI(title="DeployDock API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "deploydock-api"}


@app.get("/health/ready")
async def readiness() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus-text metrics (spec §48): deployment totals, durations, and
    agent liveness. Rendered without a client library on purpose."""
    from sqlalchemy import func, select

    from app.models import Agent, App, Deployment, Server
    from app.models.deployment import DeploymentStatus, TERMINAL_DEPLOYMENT_STATUSES

    try:
        async with AsyncSessionLocal() as session:
            status_counts = dict(
                (await session.execute(
                    select(Deployment.status, func.count()).group_by(Deployment.status)
                )).all()
            )
            duration = (await session.execute(
                select(func.count(), func.sum(Deployment.duration_seconds)).where(
                    Deployment.status.in_(TERMINAL_DEPLOYMENT_STATUSES),
                    Deployment.duration_seconds.is_not(None),
                )
            )).one()
            total_servers = await session.scalar(select(func.count()).select_from(Server))
            total_apps = await session.scalar(select(func.count()).select_from(App))
            agents = list((await session.execute(select(Agent))).scalars().all())
    except OperationalError:
        return Response(
            status_code=503,
            content="# metrics unavailable: database unreachable\n",
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    lines: list[str] = []
    lines.append("# HELP deployment_total Deployments by status.")
    lines.append("# TYPE deployment_total counter")
    for status_value in DeploymentStatus:
        lines.append(f'deployment_total{{status="{status_value.value}"}} {status_counts.get(status_value, 0)}')

    deploy_count, duration_sum = duration[0] or 0, duration[1] or 0
    lines.append("# HELP deployment_duration_seconds_sum Total deploy duration of terminal deployments.")
    lines.append("# TYPE deployment_duration_seconds_sum counter")
    lines.append(f"deployment_duration_seconds_sum {duration_sum}")
    lines.append("# TYPE deployment_duration_seconds_count counter")
    lines.append(f"deployment_duration_seconds_count {deploy_count}")

    lines.append("# HELP servers_total Registered servers.")
    lines.append("# TYPE servers_total gauge")
    lines.append(f"servers_total {total_servers or 0}")
    lines.append("# HELP apps_total Registered apps.")
    lines.append("# TYPE apps_total gauge")
    lines.append(f"apps_total {total_apps or 0}")

    lines.append("# HELP agents_online Agents with a heartbeat inside the offline window.")
    lines.append("# TYPE agents_online gauge")
    from app.services.agent_service import is_online

    online = sum(1 for agent in agents if is_online(agent, settings))
    lines.append(f"agents_online {online}")
    lines.append("# HELP agents_total Registered agents.")
    lines.append("# TYPE agents_total gauge")
    lines.append(f"agents_total {len(agents)}")

    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")


@app.exception_handler(OperationalError)
async def database_operational_error_handler(_, __: OperationalError) -> JSONResponse:
    return database_unavailable_response()


@app.exception_handler(ConnectionRefusedError)
async def database_connection_refused_handler(_, __: ConnectionRefusedError) -> JSONResponse:
    return database_unavailable_response()


def database_unavailable_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Database is unavailable. Check DATABASE_URL, confirm PostgreSQL is running, "
                "and run migrations before retrying."
            )
        },
    )
