# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build tooling is needed for the C extensions (argon2-cffi, asyncpg) and then dropped.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --no-cache-dir -e ".[redis]" \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y

# Deployments run as this user inside the container; it never needs root.
RUN useradd --create-home --uid 10001 deploydock \
    && chown -R deploydock:deploydock /app
USER deploydock

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Single worker by default: deployments run in-process, and the in-memory login
# rate limiter is per-process. Set REDIS_URL before scaling workers up.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
