# DeployDock

DeployDock is a self-hosted deployment control panel for developers and small teams who already run apps on VPS servers.

It automates your existing deployment workflow instead of forcing you to migrate to a new runtime. Connect servers, register apps, run one-click deploys, stream logs, inspect service status, restart services, and roll back failed releases from one dashboard.

DeployDock is intentionally agentless in v1:

```text
GitHub/repository -> DeployDock -> VPS/server -> existing systemd/Docker/nginx app
```

It reaches target servers over SSH on demand, runs your configured commands, streams output, saves history, and closes the connection. It does not try to own your runtime, reverse proxy, SSL setup, app structure, or secrets by default.

DeployDock currently includes:

- FastAPI backend with a health endpoint.
- Async SQLAlchemy database models and Alembic migrations.
- JWT authentication.
- Server, app, deployment, log streaming, service control, rollback, audit, and dashboard APIs.
- React + Vite dashboard UI for the MVP workflow.

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

The backend health endpoint is available at:

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

## Backend Tests

```bash
cd backend
pytest
```

## Database and Alembic

Milestone 0 includes the database session and Alembic skeleton. Database models and real migrations start in Milestone 1.

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
CORS_ORIGINS=http://localhost:5173
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

## Current Milestone

Milestone 14 adds production hardening.

Frontend pages:

- `/apps/:id`
- `/deployments`
- `/deployments/:id`

Dashboard and operations notes:

- Users can trigger a deployment from an app detail page.
- App detail pages show deployment history for that app.
- The deployments page aggregates deployment history across registered apps.
- Deployment detail pages show status, timestamps, duration, commit data, exit code, errors, and logs.
- The deployment log viewer consumes the backend SSE stream while deployments are pending or running.
- Users can pause and resume log auto-scroll.
- App detail pages include service status, restart, and recent service logs controls.
- Restart requires confirmation because it runs a command on the remote server.
- Deployment detail pages include rollback with confirmation.
- Rollback is Git-based and does not rollback database migrations.
- Dashboard shows server, app, deployment, failure, and audit summaries.
- Audit events are visible for server creation, connection tests, app changes, deployment start/success/failure, service restart, and rollback start.
- Server onboarding defaults to DeployDock-generated per-server ed25519 SSH keys.
- Secrets remain server-owned by default.

Run migrations:

```bash
cd backend
..\.venv\Scripts\alembic.exe upgrade head
```

Run backend tests:

```bash
cd backend
..\.venv\Scripts\python.exe -m pytest
```

## Production Deployment Notes

These notes assume a single Linux VPS running PostgreSQL, the FastAPI backend, a built frontend served by Nginx, and HTTPS from Nginx.

### 1. Create Production Environment Files

Backend:

```bash
cd backend
cp .env.example .env
```

Set production values:

```text
APP_ENV=production
API_HOST=127.0.0.1
API_PORT=8000
DATABASE_URL=postgresql+asyncpg://deploydock:<strong-password>@127.0.0.1:5432/deploydock
SECRET_KEY=<long-random-secret>
ACCESS_TOKEN_EXPIRE_MINUTES=60
ENCRYPTION_KEY=<long-stable-random-secret>
CORS_ORIGINS=https://deploydock.example.com
```

Frontend:

```bash
cd frontend
cp .env.example .env
```

Set:

```text
VITE_API_BASE_URL=https://deploydock.example.com
```

### 2. Install and Build

```bash
python -m venv .venv
cd backend
..\.venv\Scripts\python.exe -m pip install -e ".[dev]"
..\.venv\Scripts\alembic.exe upgrade head
```

On Linux, use:

```bash
python -m venv .venv
cd backend
../.venv/bin/python -m pip install -e ".[dev]"
../.venv/bin/alembic upgrade head
```

Frontend:

```bash
cd frontend
npm install
npm run build
```

### 3. Example systemd Service

```ini
[Unit]
Description=DeployDock API
After=network.target postgresql.service

[Service]
User=deploydock
Group=deploydock
WorkingDirectory=/opt/deploydock/backend
EnvironmentFile=/opt/deploydock/backend/.env
ExecStart=/opt/deploydock/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 4. Example Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name deploydock.example.com;

    root /opt/deploydock/frontend/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000;
    }

    location / {
        try_files $uri /index.html;
    }
}
```

Use Certbot or your preferred ACME client to enable HTTPS before using DeployDock with real SSH keys.

### 5. Backup Notes

- Back up PostgreSQL regularly with `pg_dump`.
- Back up `backend/.env` securely. Without `ENCRYPTION_KEY`, encrypted SSH keys cannot be decrypted.
- Do not store backups in a public bucket or frontend directory.
- Test restore procedures before relying on the deployment.

### 6. Security Checklist

- Use a non-root SSH user for managed servers.
- Prefer DeployDock-generated per-server ed25519 keys.
- Add only generated public keys to target server `authorized_keys`.
- Use per-server deploy keys with limited access.
- Keep `SECRET_KEY` and `ENCRYPTION_KEY` out of Git.
- Do not rotate `ENCRYPTION_KEY` without a migration plan.
- Set `CORS_ORIGINS` to the real frontend origin only.
- Put the backend behind HTTPS.
- Restrict database access to localhost or a private network.
- Review deploy commands before saving them.
- Keep OS packages, Python dependencies, and npm dependencies patched.
- Review audit logs after sensitive operations.

Roadmap security notes:

- TOTP 2FA.
- Optional IP allowlist for the dashboard.
- Persistent/distributed login rate limiting for multi-process deployments.
- Optional Go server agent for future deeper server integrations.

Milestone 14 is the final MVP milestone. Do not start a v2 plan unless explicitly requested.
