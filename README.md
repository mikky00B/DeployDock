# DeployDock

DeployDock is a self-hosted deployment control panel for developers and small teams who already run apps on VPS servers.

It automates your existing deployment workflow instead of forcing you to migrate to a new runtime. Connect servers, register apps, run one-click deploys, stream logs, inspect service status, restart services, and roll back failed releases from one dashboard.

DeployDock is intentionally agentless in v1:

```text
GitHub/repository -> DeployDock -> VPS/server -> existing systemd/Docker/nginx app
```

It reaches target servers over SSH on demand, runs your configured commands, streams output, saves history, and closes the connection. It does not try to own your runtime, reverse proxy, SSL setup, app structure, or secrets by default.

DeployDock currently includes:

- FastAPI backend with liveness and database readiness endpoints.
- Async SQLAlchemy database models and Alembic migrations.
- JWT authentication.
- Server, app, deployment, log streaming, service control, rollback, audit, and dashboard APIs.
- React + Vite dashboard UI for server onboarding, app registration, deployments, and service operations.
- Bootstrap plan generators for Django, FastAPI, Go services, and static React/Vite sites.

DeployDock is not a replacement for Vercel, Kubernetes, Docker Swarm, Coolify, Dokploy, CapRover, or Dokku. It is for existing server setups where you already deploy with commands such as:

```bash
git pull
pip install -r requirements.txt
alembic upgrade head
sudo systemctl restart app-name
```

## Project Structure

```text
backend/
  app/
  alembic/
  tests/
frontend/
  src/
```

## Backend Setup

```bash
python -m venv .venv
cd backend
..\.venv\Scripts\python.exe -m pip install -e ".[dev]"
copy .env.example .env
..\.venv\Scripts\uvicorn.exe app.main:app --reload
```

The backend liveness endpoint is available at:

```text
GET http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "deploydock-api"
}
```

The readiness endpoint checks database connectivity:

```text
GET http://127.0.0.1:8000/health/ready
```

Expected response:

```json
{
  "status": "ok",
  "database": "reachable"
}
```

## Backend Tests

```bash
cd backend
pytest
```

## Database and Alembic

DeployDock uses async SQLAlchemy models and Alembic migrations for users, servers, apps, deployments, deployment logs, and audit logs.

```bash
cd backend
alembic upgrade head
```

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend defaults to:

```text
http://127.0.0.1:5173
```

## Frontend Build

```bash
cd frontend
npm run build
```

## App Bootstrap Planner

The Apps page supports two app onboarding modes:

- Register an existing server app by entering its repository, path, deploy command, restart command, and healthcheck URL.
- Generate a setup plan for a new Django, FastAPI, Go, or static React/Vite app. The generated plan includes server commands, environment examples, systemd units, Nginx snippets, sudoers guidance, and a DeployDock app payload.

Bootstrap plans are copied into your own server workflow; DeployDock still runs only the deploy and service commands you save for the app.

## Environment Variables

The backend loads configuration from `backend/.env` through `backend/app/core/config.py`.

The frontend reads `VITE_API_BASE_URL` from `frontend/.env` through Vite's `import.meta.env`.

Backend example values live in `backend/.env.example`.

Frontend example values live in `frontend/.env.example`.

Backend variables:

```text
APP_ENV=development
API_HOST=127.0.0.1
API_PORT=8000
DATABASE_URL=postgresql+asyncpg://deploydock:deploydock@localhost:5432/deploydock
SECRET_KEY=change-me
ACCESS_TOKEN_EXPIRE_MINUTES=60
ENCRYPTION_KEY=change-me-32-byte-key
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Frontend variables:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Production guardrails:

- `APP_ENV=production` rejects weak default `SECRET_KEY` values.
- `APP_ENV=production` rejects weak/default `ENCRYPTION_KEY` values.
- `APP_ENV=production` rejects local or wildcard `CORS_ORIGINS`.
- Keep `ENCRYPTION_KEY` stable. Changing it makes stored SSH keys unreadable.

## Recommended Server Onboarding

Use one dedicated non-root deploy user per target server. Do not SSH as root.

Recommended flow:

1. Create or choose a restricted deploy user on the target server.
2. Add the server in DeployDock with name, host, SSH port, and deploy username.
3. Leave the private key field blank.
4. DeployDock generates a unique ed25519 keypair for that server.
5. Copy the generated public key into the deploy user's `authorized_keys`.
6. Click Test connection.

Example target server setup:

```bash
sudo adduser --disabled-password --gecos "" deploy
sudo mkdir -p /home/deploy/.ssh
sudo chown deploy:deploy /home/deploy/.ssh
sudo chmod 700 /home/deploy/.ssh
```

After adding the server in DeployDock, copy the generated public key:

```bash
echo '<generated-public-key>' | sudo tee -a /home/deploy/.ssh/authorized_keys
sudo chown deploy:deploy /home/deploy/.ssh/authorized_keys
sudo chmod 600 /home/deploy/.ssh/authorized_keys
```

Grant narrow sudo permissions only for commands the app needs. Example:

```text
deploy ALL=(root) NOPASSWD: /bin/systemctl restart watchdog
deploy ALL=(root) NOPASSWD: /bin/systemctl reload nginx
deploy ALL=(root) NOPASSWD: /usr/sbin/nginx -t
```

Private-key upload remains available as an advanced/manual option, but generated per-server keys are the recommended default. Keys are never reused across servers.

## Secrets and Environment Files

DeployDock v1 is not a full secrets manager.

Default recommendation:

- Keep production `.env` files on the target server.
- Use DeployDock to orchestrate deployments, restarts, logs, status checks, and rollback.
- Do not store app secrets in DeployDock unless a future optional secrets feature is explicitly added and reviewed.

## Deployment Commands

Deploy commands are configured in DeployDock for v1. This keeps the MVP compatible with existing app layouts.

Example:

```bash
set -e
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
sudo systemctl restart watchdog
```

Future roadmap: an optional `deploydock.yml` or `deploydock.yaml` manifest may be added later, but it is not required for v1.

