# DeployDock

DeployDock is a self-hosted deployment control panel for developers and small teams who already run apps on VPS servers.

It automates your existing deployment workflow instead of forcing you to migrate to a new runtime. Connect servers, register apps, run one-click deploys, stream logs, inspect service status, restart services, and roll back failed releases from one dashboard.

DeployDock is intentionally agentless in v1:

```text
GitHub/repository -> DeployDock -> VPS/server -> existing systemd/Docker/nginx app
```

It reaches target servers over SSH on demand, runs your configured commands, streams output, saves history, and closes the connection. It does not try to own your runtime, reverse proxy, SSL setup, app structure, or secrets by default.

DeployDock is not a replacement for Vercel, Kubernetes, Docker Swarm, Coolify, Dokploy, CapRover, or Dokku. It is for existing server setups where you already deploy with commands such as:

```bash
git pull
pip install -r requirements.txt
alembic upgrade head
sudo systemctl restart app-name
```

## What's included

- FastAPI backend with liveness and database readiness endpoints.
- Async SQLAlchemy models and Alembic migrations.
- JWT authentication (PyJWT, HS256) with Argon2id password hashing.
- SSH host key pinning: every connection is verified against a key you accepted.
- Server, app, deployment, log streaming, service control, rollback, audit, and dashboard APIs.
- React + Vite dashboard for server onboarding, app registration, deployments, and service operations.
- Bootstrap plan generators for Django, FastAPI, Go services, and static React/Vite sites.
- SSH private keys encrypted at rest, with key ids so the encryption key can be rotated.
- At most one active deployment per app, enforced in the database.

## Documentation

| Guide | What it covers |
| --- | --- |
| [Getting started](docs/getting-started.md) | Local setup, Docker Compose, first login |
| [Configuration](docs/configuration.md) | Every environment variable, production guardrails |
| [Server onboarding](docs/server-onboarding.md) | Deploy users, generated keys, host key pinning, sudoers |
| [Deployments](docs/deployments.md) | Deploy commands, concurrency, log streaming, rollback |
| [Security model](docs/security.md) | What DeployDock protects, what it does not, and why |
| [Operations](docs/operations.md) | Running in production, workers, key rotation, backups |
| [API reference](docs/api.md) | Endpoints, status codes, and error shapes |
| [Architecture](docs/architecture.md) | Components, request flow, and design decisions |
| [Contributing](docs/contributing.md) | Tests, linting, migrations, CI |

## Quick start with Docker Compose

```bash
cp backend/.env.example backend/.env
# Generate real secrets:
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python -c "import secrets; print('ENCRYPTION_KEY=' + secrets.token_urlsafe(48))"
# Paste both into backend/.env, then:
docker compose up --build
```

- Dashboard: <http://127.0.0.1:5173>
- API: <http://127.0.0.1:8000>
- API docs (FastAPI): <http://127.0.0.1:8000/docs>

Migrations run automatically before the API starts.

## Quick start without Docker

Requires Python 3.11+, Node 20+, and a PostgreSQL database.

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env               # then set SECRET_KEY and ENCRYPTION_KEY
alembic upgrade head
uvicorn app.main:app --reload
```

```bash
# Frontend, in a second terminal
cd frontend
npm install
cp .env.example .env
npm run dev
```

Health endpoints:

```text
GET http://127.0.0.1:8000/health        -> {"status":"ok","service":"deploydock-api"}
GET http://127.0.0.1:8000/health/ready  -> {"status":"ok","database":"reachable"}
```

See [docs/getting-started.md](docs/getting-started.md) for the full walkthrough, including your first server and first deploy.

## Project structure

```text
backend/
  app/
    api/v1/        HTTP routes
    core/          config, security, encryption, rate limiting, logging
    db/            engine and session
    models/        SQLAlchemy models
    schemas/       Pydantic request/response models
    services/      business logic (servers, apps, deployments, SSH)
    workers/       the deployment runner
  alembic/         migrations
  tests/           pytest suite
docs/              documentation
frontend/
  src/
    api/           typed API client
    hooks/         auth and deployment log streaming
    lib/bootstrap/ setup-plan generators per stack
    pages/         dashboard, servers, apps, deployments
```

## Running the checks

```bash
cd backend && ruff check . && pytest -q
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

CI runs the same checks on every push and pull request, plus an Alembic
up/down/up cycle against a real PostgreSQL service. See
[docs/contributing.md](docs/contributing.md).

## Security posture in one minute

- SSH host keys are pinned on first connection and verified on every connection after that. A mismatch aborts the connection instead of exposing your private key. Re-pinning is a deliberate, audited action.
- SSH private keys are encrypted at rest with Fernet, tagged with a key id so `ENCRYPTION_KEY` can be rotated.
- Passwords use Argon2id. Older pbkdf2 hashes are upgraded transparently on the next successful login.
- Access tokens are JWTs with a pinned algorithm, `iat`/`nbf`/`exp`/`jti`, and no server-side revocation list — keep `ACCESS_TOKEN_EXPIRE_MINUTES` short.
- `deploy_command` is arbitrary shell run on the target server. Anyone who can edit an app effectively has shell on that box. This is the product working as intended; treat DeployDock accounts accordingly.

Full detail, including the known gaps, is in [docs/security.md](docs/security.md).

## Roadmap

- Move the deployment runner out of the API process into a dedicated worker.
- Optional `deploydock.yml` manifest instead of dashboard-configured commands.
- Multi-user teams with per-app permissions.
- Optional secrets management, if it can be done without becoming a secrets manager.
