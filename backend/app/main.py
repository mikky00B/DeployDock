from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import engine

settings = get_settings()
configure_logging(settings.app_env)

app = FastAPI(title="DeployDock API")
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
