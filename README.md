# DeployDock

DeployDock is a self-hosted deployment control panel for developers and small teams who already run apps on VPS servers.

It automates your existing deployment workflow instead of forcing you to migrate to a new runtime. Connect servers, register apps, run one-click deploys, stream logs, inspect service status, restart services, and roll back failed releases from one dashboard.

DeployDock ships with two execution paths:

```text
                        DeployDock (FastAPI + PostgreSQL)
                              |                |
        path A: SSH bridge    |                |  path B: Go agent
        (nothing to install,  |                |  (daemon, outbound-only)
         runs on demand)      v                v
              existing systemd / nginx app     Docker build + health-gated switch
```

- **Path A — the SSH bridge.** DeployDock opens an SSH connection when it has something to do, runs your configured commands, streams the output, and closes. Nothing to install.
- **Path B — the agent.** A lightweight Go daemon (`deploydock-agent`) runs on the VPS, phones home over outbound HTTPS only, and executes Docker-based deployments: clone, build, start the new container, health check it, then switch traffic and stop the old container — the previous release keeps serving until the new one passes its checks.

Both paths record history, stream logs over SSE, and write to the same audit trail. DeployDock is not a replacement for Vercel, Kubernetes, Docker Swarm, Coolify, Dokploy, CapRover, or Dokku. It is for existing server setups where you already deploy with commands such as:

```bash
git pull
pip install -r requirements.txt
alembic upgrade head
sudo systemctl restart app-name
```

## What's included

- FastAPI backend with liveness, readiness, and Prometheus `/metrics` endpoints.
- Async SQLAlchemy models and Alembic migrations.
- JWT authentication (PyJWT, HS256) with Argon2id password hashing.
- SSH host key pinning: every SSH connection is verified against a key you accepted.
- Server, app, deployment, log streaming, service control, rollback, audit, and dashboard APIs.
- Agent registration, heartbeats, and a command queue for agent-driven deployments.
- Environments with encrypted, masked environment variables; domains with DNS verification.
- GitHub webhooks: HMAC-verified pushes auto-deploy (and queue behind an active release).
- Deployment cancel, a 12-state pipeline, and one-click rollback.
- Go CLI (`deploydock`) and Go agent (`deploydock-agent`).
- React + Vite dashboard for server onboarding, app registration, deployments, service operations, and a built-in guide.
- SSH private keys and environment variables encrypted at rest, with key ids so the encryption key can be rotated.
- At most one dispatchable deployment per app, enforced in the database; automatic deploys queue behind an active release.
- Bootstrap plan generators for Django, FastAPI, Go services, and static React/Vite sites.

## Documentation

| Guide | What it covers |
| --- | --- |
| [Getting started](docs/getting-started.md) | Local setup, Docker Compose, first login |
| [Configuration](docs/configuration.md) | Every environment variable, production guardrails |
| [Server onboarding](docs/server-onboarding.md) | Deploy users, generated keys, host key pinning, sudoers |
| [Deployments](docs/deployments.md) | Deploy commands, concurrency, log streaming, rollback |
| [Agent protocol](docs/agent-protocol.md) | Agent registration, tokens, heartbeat, command/event flow |
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

Requires Python 3.11+, Node 20+, and a PostgreSQL database. A Go 1.22+ toolchain is needed only to build the CLI and the agent.

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
    api/v1/        HTTP routes (auth, servers, apps, deployments, agents,
                   environments, webhooks, dashboard)
    core/          config, security, encryption, rate limiting, logging
    db/            engine and session
    models/        SQLAlchemy models
    schemas/       Pydantic request/response models
    services/      business logic (servers, apps, deployments, agents,
                   environments, webhooks, SSH)
    workers/       the SSH bridge deployment runner
  alembic/         migrations
  tests/           pytest suite
go/
  cmd/
    deploydock/        the developer CLI
    deploydock-agent/  the VPS agent
  internal/
    agent/         registration, heartbeat loop, command execution
    engine/        staged deployment engine (clone/build/start/health/proxy/cleanup)
    docker/ git/ health/ nginx/   infrastructure drivers behind interfaces
    cli/ client/ config/ system/
docs/              documentation
frontend/
  src/
    api/           typed API client
    hooks/         auth and deployment log streaming
    lib/bootstrap/ setup-plan generators per stack
    pages/         dashboard, servers, apps, deployments, docs
```

## Running the checks

```bash
cd backend && ruff check . && pytest -q
cd go && go build ./... && go vet ./... && go test ./...
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

CI runs the backend and frontend checks on every push and pull request, an
Alembic up/down/up cycle plus the concurrency-guard tests against a real
PostgreSQL service, and the Go build/vet/test suite. See
[docs/contributing.md](docs/contributing.md).

## Security posture in one minute

- SSH host keys are pinned on first connection and verified on every SSH connection after that. A mismatch aborts the connection instead of exposing your private key. Re-pinning is a deliberate, audited action. (This protects the SSH bridge; the agent path never opens SSH.)
- SSH private keys and environment variables are encrypted at rest with Fernet, tagged with a key id so `ENCRYPTION_KEY` can be rotated.
- Agent tokens are stored hashed, shown exactly once, and rotatable from the dashboard.
- GitHub webhook deliveries are HMAC-verified against a per-app secret, with replay protection by delivery id.
- Passwords use Argon2id. Older pbkdf2 hashes are upgraded transparently on the next successful login.
- Access tokens are JWTs with a pinned algorithm, `iat`/`nbf`/`exp`/`jti`, and no server-side revocation list — keep `ACCESS_TOKEN_EXPIRE_MINUTES` short.
- `deploy_command` is arbitrary shell run on the target server. Anyone who can edit an app effectively has shell on that box. This is the product working as intended; treat DeployDock accounts accordingly.

Full detail, including the known gaps, is in [docs/security.md](docs/security.md).

## Roadmap

- Multi-user teams with per-app permissions.
- Managed SSL issuance (Let's Encrypt) on top of the domain verification flow.
- A dedicated queue worker for SSH-bridge deployments (agent-driven deployments already execute on the VPS).
- Notifications on deployment success and failure.

## License

MIT — see [LICENSE](LICENSE).

<!-- CI workflow validation trigger -->
