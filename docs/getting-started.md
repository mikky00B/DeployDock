# Getting started

This walks from an empty checkout to a first successful deployment.

## Requirements

- Python 3.11 or 3.12
- Node 20 or newer
- PostgreSQL 14 or newer
- A VPS you can already SSH into, with an app you already deploy by hand

DeployDock automates a workflow you already have. If you cannot deploy the app
manually with a few shell commands, get that working first — DeployDock runs
those same commands.

## Option A: Docker Compose

```bash
cp backend/.env.example backend/.env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"   # ENCRYPTION_KEY
```

Put both values in `backend/.env`, then:

```bash
docker compose up --build
```

This starts PostgreSQL, Redis, runs `alembic upgrade head`, then the API and the
dashboard. Ports are bound to `127.0.0.1` only.

| Service | URL |
| --- | --- |
| Dashboard | <http://127.0.0.1:5173> |
| API | <http://127.0.0.1:8000> |
| Interactive API docs | <http://127.0.0.1:8000/docs> |

To stop and keep data: `docker compose down`. To also drop the database:
`docker compose down -v`.

## Option B: Local processes

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env` and set at minimum `DATABASE_URL`, `SECRET_KEY`, and
`ENCRYPTION_KEY`. Then:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

Verify:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/ready
```

If `/health/ready` returns 503, the API is running but cannot reach the
database. Check `DATABASE_URL` and that PostgreSQL is up.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

The dashboard runs on <http://127.0.0.1:5173>. Leave `VITE_API_BASE_URL` unset
in development: API calls go to the dashboard origin itself and Vite proxies
`/api` to `http://127.0.0.1:8000`, so no CORS is involved. The value is read at
build time, so setting or changing it requires a restart of `npm run dev` (or a
rebuild for production).

## First run

### 1. Create your account

Open the dashboard and register. The first account is created through the same
public `/api/v1/auth/register` endpoint as any other; there is no separate admin
bootstrap. If you do not want the endpoint open, put the API behind an
allowlist or a reverse-proxy auth layer after you have registered.

### 2. Add a server

On **Servers**, add the target machine:

- **Name** — anything you recognise.
- **Host** and **Port** — where the server answers SSH.
- **Deploy username** — a dedicated non-root user, e.g. `deploy`.
- **Private key** — leave blank. DeployDock generates a unique ed25519
  keypair for this server and shows you the public half.

Copy the generated public key into that user's `authorized_keys` on the server,
then press **Test connection**.

On the first successful test, DeployDock pins the server's SSH host key and
shows its fingerprint. Verify it against the server itself before you trust it:

```bash
# On a machine you trust, or on the server console:
ssh-keyscan -t ed25519 your-server.example.com | ssh-keygen -lf -
```

If the fingerprints match, you're done. If they do not, stop — something is
intercepting the connection. See
[docs/server-onboarding.md](server-onboarding.md).

### 3. Register an app

On **Apps**, either register an app you already deploy, or use the bootstrap
planner to generate a setup plan for a new Django, FastAPI, Go, or static
React/Vite app.

For an existing app you need:

- **Repository URL** and **branch** — recorded for reference.
- **App path** — the checkout directory on the server, e.g. `/opt/watchdog`.
- **Deploy command** — the shell you would run by hand.
- **Service name** or **restart command** — how the app gets restarted.
- **Healthcheck URL** — optional on the SSH path. Agent-driven deployments
  probe it after starting the new container and only switch traffic when it
  passes.
- **Container port** — required for agent-driven deployments; ignored by the
  SSH bridge. CPU and memory limits are optional, agent-only.

Example deploy command:

```bash
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
sudo systemctl restart watchdog
```

DeployDock wraps this in `set -e` and `cd <app_path>`, so a failing step aborts
the deploy rather than continuing into a restart.

### 4. Deploy

Press **Deploy**. You get a live log stream, an exit code, the commit SHA before
and after, and a duration. Failed deploys keep their logs; the previous commit
is recorded so a rollback has somewhere to go. A deploy that is still running
can be canceled from the deployment page.

Only one dispatchable deployment per app runs at a time. A second dashboard
attempt while one is in flight returns `409 Conflict` rather than racing on the
same checkout; pushes from a configured GitHub webhook queue instead and start
automatically when the active deployment finishes.

## Next steps

- [Server onboarding](server-onboarding.md) — hardening the deploy user
- [Deployments](deployments.md) — cancel, queueing, rollback, log streaming, service control
- [Agent protocol](agent-protocol.md) — install the agent for Docker-based, zero-downtime deploys
- [Configuration](configuration.md) — every setting and what it does
- [Operations](operations.md) — production checklist, key rotation, backups
