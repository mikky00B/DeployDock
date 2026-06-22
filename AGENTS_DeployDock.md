# AGENTS.md — DeployDock

## Project Name

DeployDock

## Project Vision

DeployDock is a self-hosted deployment control panel for developers, freelancers, and small agencies who deploy applications to VPS/cloud servers.

The goal is not to compete with Vercel, Render, Railway, Coolify, Dokploy, or Kubernetes platforms.

The goal is to solve a simpler and very common problem:

> “I already have apps running on my own server. I want a clean dashboard to deploy, restart, view logs, track history, and rollback without manually SSH-ing every time.”

DeployDock should feel like a practical operations cockpit for VPS-hosted applications.

The first version should focus on:

- Connecting to servers over SSH.
- Registering apps/projects deployed on those servers.
- Defining deployment commands.
- Running one-click deployments.
- Streaming deployment logs.
- Saving deployment history.
- Checking service status.
- Restarting services.
- Supporting simple rollback.

Do not overbuild. Do not add Kubernetes, billing, teams, preview deployments, or complex CI/CD pipelines in the first version.

---

# 1. High-Level Product Description

DeployDock is a dashboard where a developer can:

1. Add a VPS/server.
2. Test SSH connection.
3. Add an application hosted on that server.
4. Define deployment commands for the app.
5. Click “Deploy”.
6. Watch live logs.
7. See whether the deployment succeeded or failed.
8. View deployment history.
9. Restart or inspect the app service.
10. Roll back to a previous deployed commit.

The intended first-user workflow is:

```text
Add Server → Add App → Configure Commands → Deploy → Watch Logs → Review Result
```

The product should be designed around this exact workflow.

---

# 2. Recommended Stack

Use this stack for the MVP:

```text
Backend: FastAPI
Frontend: React + Vite + TypeScript
Database: PostgreSQL
ORM: SQLAlchemy 2.x async
Migrations: Alembic
Auth: Session or JWT-based auth
SSH: AsyncSSH preferred; Paramiko acceptable if simpler
Background jobs: Start simple with an internal async task runner
Live logs: Server-Sent Events or WebSocket
Testing: Pytest for backend, Vitest/React Testing Library for frontend
Deployment target: Linux VPS
```

## Why FastAPI for v1?

FastAPI is the right choice for DeployDock v1 because the first version is mainly about product workflow, database models, SSH orchestration, auth, deployment history, logs, and dashboard APIs.

Do not start with a Go-only backend unless specifically instructed later.

A future v2 may introduce a Go-based remote agent, but the MVP should stay FastAPI-first.

---

# 3. Long-Term Architecture Direction

The MVP should use direct SSH from the DeployDock backend to the target server.

Long term, DeployDock may evolve into:

```text
FastAPI Control Plane + Go Server Agent
```

Where:

- FastAPI handles users, dashboard, database, GitHub integration, app configuration, deployment records, and permissions.
- A Go agent installed on each server handles deployment execution, service control, log streaming, and server metrics.

But do not implement the Go agent in the MVP unless explicitly requested.

---

# 4. Core Principles for the Coding Agent

## 4.1 Build in Milestones

Do not build the entire application in one large pass.

This project must be implemented in milestones so the owner can study and understand the code after each milestone.

At the end of every milestone, the agent must:

1. Summarize what was built.
2. List files changed.
3. Explain important design decisions.
4. Explain how to run/test the milestone.
5. Mention what should be studied before moving on.
6. Stop and wait for approval before continuing.

Never continue to the next milestone without user approval.

## 4.2 Keep the Code Understandable

Prefer clear code over clever code.

Use simple, explicit naming.

Avoid premature abstractions.

Do not introduce unnecessary frameworks, libraries, services, or patterns.

Every important module should be readable by a junior-to-mid backend developer.

## 4.3 Security First

DeployDock runs commands on remote servers. Treat this as dangerous by default.

Do not casually execute arbitrary shell commands without clear boundaries.

Security rules:

- Never log private SSH keys.
- Never return private keys through API responses.
- Encrypt sensitive credentials before storing them.
- Redact secrets in logs where possible.
- Use a non-root deploy user where possible.
- Validate ownership before accessing any server, app, deployment, or log.
- Do not allow one user to access another user’s infrastructure.
- Do not expose dangerous admin operations without authentication.
- Do not silently ignore command failures.
- Do not store plaintext passwords or secrets.

## 4.4 Preserve Learning Value

This project is also for learning.

When creating code, prefer a structure that makes it easy to inspect:

- models
- schemas
- services
- routes
- workers
- utilities
- tests

Avoid hiding too much logic inside giant helper functions.

Each feature should be understandable in isolation.

## 4.5 Test After Every Milestone

Each milestone must include tests where practical.

At minimum:

- Backend routes should have tests.
- Services should have unit tests when external systems can be mocked.
- Database behavior should be tested where important.
- Frontend critical flows should have basic tests once frontend begins.

After each milestone, the agent should provide the exact commands to run tests.

---

# 5. Product Scope

## 5.1 MVP Features

The MVP should include:

- User authentication.
- Server registration.
- SSH connection test.
- Application registration.
- Deployment command configuration.
- One-click deploy.
- Live deployment log streaming.
- Deployment history.
- Deployment status: pending, running, success, failed, canceled.
- Basic service status check.
- Service restart.
- Simple rollback using previous Git commit.
- Audit log for important actions.

## 5.2 Features to Avoid in MVP

Do not implement these in the MVP:

- Billing/subscriptions.
- Team accounts.
- Kubernetes support.
- Docker Swarm support.
- Full CI pipeline builder.
- Complex GitHub App integration.
- Preview deployments.
- Multi-region deployments.
- Container registry management.
- Advanced secrets manager.
- Public marketplace/templates.
- Notification integrations.
- AI deployment debugging.
- Terraform/provisioning.

These can be considered later.

---

# 6. Domain Model

The initial domain model should be simple.

## 6.1 User

Represents a DeployDock account.

Suggested fields:

```text
id
email
hashed_password
full_name
is_active
created_at
updated_at
```

## 6.2 Server

Represents a VPS/cloud server.

Suggested fields:

```text
id
owner_id
name
host
port
username
auth_type
encrypted_private_key
private_key_fingerprint
status
last_connection_check_at
last_connection_error
created_at
updated_at
```

Notes:

- `encrypted_private_key` must never be returned directly through APIs.
- `private_key_fingerprint` can be shown to the user.
- `status` may be unknown, connected, unreachable.

## 6.3 App

Represents an application deployed on a server.

Suggested fields:

```text
id
owner_id
server_id
name
repository_url
branch
app_path
service_name
deploy_command
restart_command
healthcheck_url
current_commit
last_successful_commit
created_at
updated_at
```

Notes:

- `deploy_command` is the command or script run during deployment.
- `restart_command` can default to `sudo systemctl restart <service_name>`.
- `service_name` is optional but useful for status/restart/logs.

## 6.4 Deployment

Represents one deployment attempt.

Suggested fields:

```text
id
owner_id
app_id
server_id
status
commit_sha
previous_commit_sha
started_at
finished_at
duration_seconds
triggered_by
exit_code
error_message
created_at
updated_at
```

Suggested statuses:

```text
pending
running
success
failed
canceled
```

## 6.5 DeploymentLog

Represents log lines from a deployment.

Suggested fields:

```text
id
deployment_id
stream
line
sequence
created_at
```

Where `stream` can be:

```text
stdout
stderr
system
```

## 6.6 AuditLog

Represents important user actions.

Suggested fields:

```text
id
owner_id
action
entity_type
entity_id
metadata_json
created_at
```

Examples:

```text
server.created
server.connection_tested
app.created
deployment.started
deployment.succeeded
deployment.failed
service.restarted
rollback.started
```

---

# 7. Backend API Shape

Use `/api/v1`.

## 7.1 Auth Routes

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

## 7.2 Server Routes

```text
POST   /api/v1/servers
GET    /api/v1/servers
GET    /api/v1/servers/{server_id}
PATCH  /api/v1/servers/{server_id}
DELETE /api/v1/servers/{server_id}
POST   /api/v1/servers/{server_id}/test-connection
```

## 7.3 App Routes

```text
POST   /api/v1/apps
GET    /api/v1/apps
GET    /api/v1/apps/{app_id}
PATCH  /api/v1/apps/{app_id}
DELETE /api/v1/apps/{app_id}
GET    /api/v1/apps/{app_id}/status
POST   /api/v1/apps/{app_id}/restart
GET    /api/v1/apps/{app_id}/logs
```

## 7.4 Deployment Routes

```text
POST /api/v1/apps/{app_id}/deploy
GET  /api/v1/apps/{app_id}/deployments
GET  /api/v1/deployments/{deployment_id}
GET  /api/v1/deployments/{deployment_id}/logs
GET  /api/v1/deployments/{deployment_id}/stream
POST /api/v1/deployments/{deployment_id}/rollback
```

The stream endpoint may use SSE or WebSocket.

SSE is acceptable for MVP because deployment logs are server-to-client only.

---

# 8. Suggested Backend Folder Structure

Use a clean modular structure.

```text
backend/
  app/
    __init__.py
    main.py

    core/
      config.py
      security.py
      encryption.py
      logging.py

    db/
      base.py
      session.py

    models/
      user.py
      server.py
      app.py
      deployment.py
      deployment_log.py
      audit_log.py

    schemas/
      auth.py
      user.py
      server.py
      app.py
      deployment.py
      deployment_log.py

    api/
      deps.py
      v1/
        router.py
        auth.py
        servers.py
        apps.py
        deployments.py

    services/
      auth_service.py
      server_service.py
      app_service.py
      ssh_service.py
      deployment_service.py
      log_service.py
      audit_service.py

    workers/
      deployment_runner.py

    tests/
      conftest.py
      test_auth.py
      test_servers.py
      test_apps.py
      test_deployments.py

  alembic/
  alembic.ini
  pyproject.toml
  .env.example
```

---

# 9. Suggested Frontend Folder Structure

```text
frontend/
  src/
    main.tsx
    App.tsx

    api/
      client.ts
      auth.ts
      servers.ts
      apps.ts
      deployments.ts

    components/
      layout/
        AppShell.tsx
        Sidebar.tsx
        Header.tsx

      common/
        Button.tsx
        Input.tsx
        Badge.tsx
        Card.tsx
        EmptyState.tsx
        ConfirmDialog.tsx

      servers/
        ServerCard.tsx
        ServerForm.tsx
        ServerConnectionStatus.tsx

      apps/
        AppCard.tsx
        AppForm.tsx
        AppStatusBadge.tsx

      deployments/
        DeploymentTable.tsx
        DeploymentLogViewer.tsx
        DeploymentStatusBadge.tsx

    pages/
      LoginPage.tsx
      RegisterPage.tsx
      DashboardPage.tsx
      ServersPage.tsx
      ServerDetailPage.tsx
      AppsPage.tsx
      AppDetailPage.tsx
      DeploymentDetailPage.tsx
      SettingsPage.tsx

    hooks/
      useAuth.ts
      useDeploymentStream.ts

    types/
      auth.ts
      server.ts
      app.ts
      deployment.ts

    utils/
      formatDate.ts
      statusLabels.ts
```

---

# 10. Milestone Plan

The project must be implemented in milestones.

Each milestone should produce a usable checkpoint.

Do not jump ahead.

---

## Milestone 0 — Repository and Project Foundation

### Goal

Set up the basic monorepo structure and development foundation.

### Scope

Create:

```text
deploydock/
  backend/
  frontend/
  README.md
  AGENTS.md
  .gitignore
```

Backend setup:

- FastAPI app boots successfully.
- Health endpoint exists.
- Config loading exists.
- Basic logging exists.
- PostgreSQL connection config exists.
- Alembic initialized.
- Test setup initialized.

Frontend setup:

- React + Vite + TypeScript app boots successfully.
- Basic layout placeholder.
- API client placeholder.
- Environment config placeholder.

### Backend Health Endpoint

```text
GET /health
```

Should return:

```json
{
  "status": "ok",
  "service": "deploydock-api"
}
```

### Done Criteria

- Backend starts locally.
- Frontend starts locally.
- Backend health endpoint works.
- Initial test passes.
- README explains how to run both apps.

### Study Checkpoint

Before moving on, study:

- backend/app/main.py
- backend/app/core/config.py
- backend/app/db/session.py
- frontend/src/main.tsx
- frontend/src/App.tsx

### Agent Must Stop After This Milestone

Do not proceed to Milestone 1 until the user approves.

---

## Milestone 1 — Database Models and Alembic Migrations

### Goal

Create the core database structure.

### Scope

Implement models for:

- User
- Server
- App
- Deployment
- DeploymentLog
- AuditLog

Create Alembic migration.

### Requirements

- Use SQLAlchemy 2.x style.
- Use async database sessions.
- Use UUID primary keys if preferred, otherwise integer IDs are acceptable.
- Add created_at and updated_at timestamps.
- Add useful indexes:
  - user email
  - server owner_id
  - app owner_id
  - deployment app_id
  - deployment status
  - deployment_log deployment_id + sequence

### Done Criteria

- Migration runs successfully.
- Tables are created.
- Tests confirm model creation works.
- Relationships are clear.

### Study Checkpoint

Study:

- How SQLAlchemy models are declared.
- How relationships work.
- How Alembic migrations are generated and applied.
- Why each table exists.

### Agent Must Stop After This Milestone

Do not proceed to Milestone 2 until the user approves.

---

## Milestone 2 — Authentication

### Goal

Add user registration, login, logout, and current-user retrieval.

### Scope

Implement:

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

### Requirements

- Passwords must be hashed.
- Do not store plaintext passwords.
- Use JWT or secure cookie sessions.
- Add auth dependency for protected routes.
- Add tests for register/login/me.
- Validate email format.
- Prevent duplicate emails.

### Done Criteria

- User can register.
- User can login.
- User can fetch their own profile.
- Protected route rejects unauthenticated user.
- Auth tests pass.

### Study Checkpoint

Study:

- Password hashing.
- Token/session creation.
- FastAPI dependencies.
- How current user is loaded.
- How protected routes work.

### Agent Must Stop After This Milestone

Do not proceed to Milestone 3 until the user approves.

---

## Milestone 3 — Server Management

### Goal

Allow users to add and manage remote servers.

### Scope

Implement:

```text
POST   /api/v1/servers
GET    /api/v1/servers
GET    /api/v1/servers/{server_id}
PATCH  /api/v1/servers/{server_id}
DELETE /api/v1/servers/{server_id}
POST   /api/v1/servers/{server_id}/test-connection
```

### Requirements

Server creation should accept:

```text
name
host
port
username
private_key
```

Important:

- Store private key encrypted.
- Never return private key in API responses.
- Return private key fingerprint if possible.
- User can only access their own servers.
- Add tests for ownership isolation.

### SSH Connection Test

The test connection endpoint should:

1. Decrypt the stored SSH key.
2. Attempt to connect to the server.
3. Run a safe command like:

```bash
echo deploydock-ok
```

4. Store connection status.
5. Return success/failure.

### Done Criteria

- User can create a server.
- Private key is encrypted.
- API response does not expose private key.
- User can list only their own servers.
- Connection test endpoint exists.
- SSH service is isolated and mockable in tests.

### Study Checkpoint

Study:

- Encryption helper.
- Server model and schemas.
- Server routes.
- SSH service interface.
- Ownership checks.

### Agent Must Stop After This Milestone

Do not proceed to Milestone 4 until the user approves.

---

## Milestone 4 — App/Project Management

### Goal

Allow users to register deployable applications.

### Scope

Implement:

```text
POST   /api/v1/apps
GET    /api/v1/apps
GET    /api/v1/apps/{app_id}
PATCH  /api/v1/apps/{app_id}
DELETE /api/v1/apps/{app_id}
```

### App Fields

Support:

```text
name
server_id
repository_url
branch
app_path
service_name
deploy_command
restart_command
healthcheck_url
```

### Requirements

- App must belong to the current user.
- App must be attached to one of the user’s servers.
- User cannot attach app to another user’s server.
- Deploy command can be multiline.
- Restart command can be optional.
- Add validation for dangerous empty commands.

### Done Criteria

- User can create an app.
- User can list their apps.
- User can update app settings.
- User can delete app.
- Ownership tests pass.

### Study Checkpoint

Study:

- App model.
- App schemas.
- How server ownership is validated.
- How multiline deploy commands are stored.
- How route tests are structured.

### Agent Must Stop After This Milestone

Do not proceed to Milestone 5 until the user approves.

---

## Milestone 5 — Deployment Runner v1

### Goal

Implement the first working deployment execution flow.

### Scope

Implement:

```text
POST /api/v1/apps/{app_id}/deploy
GET  /api/v1/apps/{app_id}/deployments
GET  /api/v1/deployments/{deployment_id}
GET  /api/v1/deployments/{deployment_id}/logs
```

### Deployment Flow

When a user clicks deploy:

1. Validate app ownership.
2. Create deployment record with status `pending`.
3. Start deployment runner.
4. Mark deployment as `running`.
5. Connect to server over SSH.
6. Change into app path.
7. Capture current Git commit if available.
8. Run deploy command.
9. Save stdout/stderr as deployment logs.
10. Store exit code.
11. Mark deployment as `success` or `failed`.
12. Store finish time and duration.

### Important Implementation Rule

For MVP, it is acceptable to run deployments using a simple background task.

Do not introduce Celery or Redis unless explicitly needed.

Use a service class so it can later be replaced by a real worker.

### Command Execution

Deployment command should run in the app path.

Example:

```bash
cd /opt/watchdog && bash -lc '<deploy command>'
```

Be careful with quoting.

A safer approach is to write the deploy command to a temporary script on the server and execute the script.

For example:

```bash
cat > /tmp/deploydock-<deployment_id>.sh <<'EOF'
set -e
cd /opt/myapp
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
sudo systemctl restart myapp
EOF

bash /tmp/deploydock-<deployment_id>.sh
rm /tmp/deploydock-<deployment_id>.sh
```

### Done Criteria

- User can trigger deployment.
- Deployment status changes correctly.
- Logs are saved.
- Failed commands mark deployment as failed.
- Deployment history is visible through API.
- Tests cover success and failure using mocked SSH.

### Study Checkpoint

Study:

- Deployment service.
- Deployment runner.
- Log saving.
- Status transitions.
- How SSH is mocked in tests.

### Agent Must Stop After This Milestone

Do not proceed to Milestone 6 until the user approves.

---

## Milestone 6 — Live Deployment Log Streaming

### Goal

Allow users to watch logs while deployment is running.

### Scope

Implement:

```text
GET /api/v1/deployments/{deployment_id}/stream
```

Use either:

- Server-Sent Events, preferred for MVP.
- WebSocket, acceptable if already simpler in the codebase.

### Requirements

- Stream existing log lines first.
- Continue streaming new log lines until deployment finishes.
- Stop stream when deployment reaches success, failed, or canceled.
- Verify user owns the deployment before streaming logs.
- Include heartbeat events to keep connection alive.

### SSE Event Example

```text
event: log
data: {"stream":"stdout","line":"Installing dependencies...","sequence":12}

event: status
data: {"status":"success"}
```

### Done Criteria

- Stream endpoint works.
- User receives logs as deployment runs.
- Stream closes cleanly after deployment finishes.
- Tests cover access control and basic stream behavior where practical.

### Study Checkpoint

Study:

- SSE basics.
- Log polling or pub/sub implementation.
- Deployment status transitions.
- Frontend consumption plan.

### Agent Must Stop After This Milestone

Do not proceed to Milestone 7 until the user approves.

---

## Milestone 7 — Service Status, Logs, and Restart

### Goal

Add operational controls for an app service.

### Scope

Implement:

```text
GET  /api/v1/apps/{app_id}/status
POST /api/v1/apps/{app_id}/restart
GET  /api/v1/apps/{app_id}/logs
```

### Service Status

If `service_name` is set, run:

```bash
systemctl is-active <service_name>
```

Return:

```json
{
  "service_name": "watchdog",
  "status": "active"
}
```

### Restart

If `restart_command` is set, run it.

Otherwise, if `service_name` is set, run:

```bash
sudo systemctl restart <service_name>
```

### Recent Logs

If `service_name` is set, run:

```bash
journalctl -u <service_name> -n 100 --no-pager
```

### Requirements

- Validate ownership.
- Avoid exposing secrets.
- Save audit logs for restart.
- Handle missing service_name gracefully.

### Done Criteria

- User can check app service status.
- User can restart app service.
- User can view recent service logs.
- Tests use mocked SSH.

### Study Checkpoint

Study:

- App operational endpoints.
- How commands are built safely.
- How audit logs are written.
- Error handling for unavailable services.

### Agent Must Stop After This Milestone

Do not proceed to Milestone 8 until the user approves.

---

## Milestone 8 — Simple Rollback

### Goal

Allow rollback to the previous successful commit.

### Scope

Implement:

```text
POST /api/v1/deployments/{deployment_id}/rollback
```

### Rollback Behavior

For MVP, rollback should:

1. Validate ownership.
2. Find the app.
3. Find the previous successful deployment commit.
4. Create a new deployment record with type/metadata indicating rollback.
5. SSH into the server.
6. Run:

```bash
cd <app_path>
git fetch
git checkout <previous_commit>
<restart_command>
```

7. Mark rollback as success or failed.
8. Save logs.

### Requirements

- Do not rollback if no previous successful commit exists.
- Store rollback logs.
- Store audit log.
- Be honest in the UI/API that this is Git-based rollback, not database rollback.
- Do not attempt to reverse database migrations.

### Done Criteria

- Rollback endpoint works.
- Rollback deployment is recorded.
- Logs are saved.
- Failure cases are handled.
- Tests cover no previous commit and successful rollback.

### Study Checkpoint

Study:

- How previous deployments are queried.
- Why rollback is limited.
- Why database rollback is not automatic.
- How deployment records represent rollback.

### Agent Must Stop After This Milestone

Do not proceed to Milestone 9 until the user approves.

---

## Milestone 9 — Frontend Foundation and Auth UI

### Goal

Start the frontend dashboard.

### Scope

Implement:

- Login page.
- Register page.
- Auth state.
- Protected routes.
- App shell layout.
- Sidebar navigation.
- Dashboard placeholder.

### Pages

```text
/login
/register
/dashboard
/servers
/apps
/deployments
```

### Done Criteria

- User can register from UI.
- User can login from UI.
- Authenticated user sees dashboard.
- Unauthenticated user is redirected to login.
- Frontend API client is organized.

### Study Checkpoint

Study:

- API client.
- Auth state management.
- Protected route implementation.
- App shell layout.

### Agent Must Stop After This Milestone

Do not proceed to Milestone 10 until the user approves.

---

## Milestone 10 — Server and App UI

### Goal

Allow users to manage servers and apps from the dashboard.

### Scope

Implement:

- Servers page.
- Add server form.
- Server detail page.
- Test connection button.
- Apps page.
- Add app form.
- App detail page.
- App settings edit form.

### UX Requirements

The UI should clearly show:

- Server connection status.
- App server.
- Branch.
- App path.
- Service name.
- Last deployment status if available.

### Done Criteria

- User can create server from UI.
- User can test server connection from UI.
- User can create app from UI.
- User can view app details.
- User can edit app configuration.

### Study Checkpoint

Study:

- Form handling.
- API calls.
- Error display.
- Loading states.
- Data fetching pattern.

### Agent Must Stop After This Milestone

Do not proceed to Milestone 11 until the user approves.

---

## Milestone 11 — Deployment UI

### Goal

Allow user to deploy apps and view deployment history from UI.

### Scope

Implement:

- Deploy button.
- Deployment history table.
- Deployment detail page.
- Deployment status badges.
- Log viewer.
- Live log stream from SSE/WebSocket.

### UX Requirements

Deployment detail should show:

```text
Status
Started time
Finished time
Duration
Commit SHA
Exit code
Logs
```

The log viewer should:

- Preserve line breaks.
- Auto-scroll while running.
- Allow user to pause auto-scroll.
- Clearly differentiate stdout, stderr, and system messages if possible.

### Done Criteria

- User can deploy from UI.
- User can watch logs.
- User can view previous deployment logs.
- Failed deployment is visually obvious.
- Success deployment is visually obvious.

### Study Checkpoint

Study:

- Deployment flow from frontend to backend.
- Live stream hook.
- Log viewer component.
- Status rendering.

### Agent Must Stop After This Milestone

Do not proceed to Milestone 12 until the user approves.

---

## Milestone 12 — Service Controls and Rollback UI

### Goal

Add operational controls to the app detail page.

### Scope

Implement UI for:

- Check service status.
- Restart service.
- View recent service logs.
- Trigger rollback.

### Requirements

- Restart should require confirmation.
- Rollback should require confirmation.
- Explain rollback limitation in UI:
  - It reverts code to a previous Git commit.
  - It does not rollback database migrations automatically.
- Show operation results clearly.

### Done Criteria

- User can restart service from UI.
- User can view recent service logs.
- User can rollback from UI.
- Dangerous operations require confirmation.

### Study Checkpoint

Study:

- Confirmation dialog pattern.
- Service operations.
- Rollback flow.
- Error handling for risky actions.

### Agent Must Stop After This Milestone

Do not proceed to Milestone 13 until the user approves.

---

## Milestone 13 — Audit Logs and Dashboard Polish

### Goal

Make the app feel like a real operations dashboard.

### Scope

Implement:

- Dashboard overview.
- Recent deployments.
- Recent audit logs.
- App health summary.
- Server summary.
- Empty states.
- Better error messages.
- Loading skeletons/spinners.

### Dashboard Should Show

```text
Total servers
Connected servers
Total apps
Running apps
Recent deployments
Recent failures
Recent audit events
```

### Done Criteria

- Dashboard is useful.
- Audit log is visible.
- Empty states guide the user.
- UI feels coherent.

### Study Checkpoint

Study:

- How dashboard data is composed.
- Audit log model and API.
- UI polish structure.
- Empty state components.

### Agent Must Stop After This Milestone

Do not proceed to Milestone 14 until the user approves.

---

## Milestone 14 — Production Hardening

### Goal

Prepare DeployDock for real deployment.

### Scope

Add:

- Environment-based config.
- Strong production secrets.
- CORS config.
- Secure cookies if using cookie auth.
- Rate limiting for auth endpoints if practical.
- Dockerfile or systemd deployment docs.
- Nginx reverse proxy example.
- Database migration instructions.
- Backup notes.
- Basic security checklist.
- .env.example.

### Done Criteria

- App can be deployed on a VPS.
- README includes production setup.
- Environment variables are documented.
- Security concerns are documented.
- Tests pass.

### Study Checkpoint

Study:

- Deployment docs.
- Nginx config.
- Environment variables.
- Production security checklist.

### Agent Must Stop After This Milestone

Do not proceed unless a new v2 plan is requested.

---

# 11. Security Details

## 11.1 SSH Key Storage

Private SSH keys must be encrypted before being stored.

Use an app-level encryption key from environment variables.

Example environment variable:

```text
DEPLOYDOCK_SECRET_KEY=
DEPLOYDOCK_ENCRYPTION_KEY=
```

Do not generate a new encryption key on every app startup in production, because previously stored SSH keys would become unreadable.

## 11.2 Command Execution Risk

Deployment commands are user-provided. This is expected because DeployDock is a self-hosted tool.

Still:

- Do not run commands on DeployDock’s own host unless intentionally configured as a target server.
- Make clear in docs that users should use a restricted deploy user.
- Prefer project-specific directories like `/opt/myapp`.
- Avoid encouraging root SSH access.
- Log command output carefully.
- Do not display secrets in frontend logs if they can be detected.

## 11.3 Ownership and Access Control

Every database query for protected resources must check owner_id.

Never fetch by ID alone.

Bad:

```python
app = await session.get(App, app_id)
```

Better:

```python
app = await get_app_for_user(session, app_id=app_id, user_id=current_user.id)
```

This applies to:

- servers
- apps
- deployments
- logs
- audit logs

## 11.4 Sensitive Response Rules

API responses must not include:

- private SSH keys
- raw encrypted keys
- password hashes
- secret environment values
- internal encryption keys
- full server credentials

---

# 12. Deployment Command Design

DeployDock should support multiline commands.

Example FastAPI app deploy command:

```bash
set -e
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
sudo systemctl restart watchdog
```

Example React/Vite frontend deploy command:

```bash
set -e
git pull origin main
npm install
npm run build
sudo systemctl reload nginx
```

Example Go app deploy command:

```bash
set -e
git pull origin main
go build -o bin/gatekeeper ./cmd/server
sudo systemctl restart gatekeeper
```

For execution, prefer writing the command to a temporary script and running the script remotely.

This avoids quoting issues with complex multiline commands.

---

# 13. Logging Design

Deployment logs should be saved line-by-line.

Each log line should have:

```text
deployment_id
sequence
stream
line
created_at
```

The frontend should not have to parse one giant text blob.

This makes it easier to:

- stream logs
- search logs later
- display stdout/stderr differently
- resume log viewing after page refresh

---

# 14. Status Design

Deployment statuses:

```text
pending
running
success
failed
canceled
```

Server statuses:

```text
unknown
connected
unreachable
```

Service statuses:

```text
active
inactive
failed
unknown
```

Status transitions must be explicit.

For deployment:

```text
pending → running → success
pending → running → failed
pending → canceled
running → canceled
```

Do not mark a deployment successful unless the command exits with code 0.

---

# 15. Error Handling

Errors should be useful but safe.

Good error:

```text
SSH connection failed: authentication failed for deploy@123.45.67.89
```

Bad error:

```text
Private key -----BEGIN OPENSSH PRIVATE KEY-----...
```

For API errors, return consistent structure:

```json
{
  "detail": "Server not found"
}
```

or, if using custom error format:

```json
{
  "error": {
    "code": "SERVER_NOT_FOUND",
    "message": "Server not found"
  }
}
```

Keep it simple for MVP.

---

# 16. Testing Strategy

## Backend Tests

Use pytest.

Test categories:

1. Auth tests.
2. Server CRUD tests.
3. App CRUD tests.
4. Ownership isolation tests.
5. Deployment service tests with mocked SSH.
6. Deployment log tests.
7. Rollback tests.
8. Audit log tests.

Do not require a real SSH server in normal tests.

Mock the SSH service.

## Frontend Tests

Use Vitest and React Testing Library.

Test:

- Login form.
- Server form.
- App form.
- Deployment table.
- Log viewer.
- Protected route behavior where practical.

Do not overdo frontend tests early.

---

# 17. Documentation Requirements

Every milestone should update README when needed.

README should eventually include:

- What DeployDock is.
- What problem it solves.
- Local development setup.
- Backend setup.
- Frontend setup.
- Environment variables.
- Database migration commands.
- How to add a server.
- How to add an app.
- Example deploy commands.
- Security warnings.
- Production deployment guide.

---

# 18. Suggested Environment Variables

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

For frontend:

```text
VITE_API_BASE_URL=http://localhost:8000
```

---

# 19. UI Direction

DeployDock should look clean, serious, and operational.

Design mood:

```text
GitHub Actions + Linear + Railway dashboard + server admin panel
```

Avoid making it too colorful or playful.

Important UI elements:

- status badges
- deployment cards
- log terminal
- server cards
- app cards
- confirmation dialogs
- empty states
- recent activity list

## Suggested Pages

```text
/login
/register
/dashboard
/servers
/servers/:id
/apps
/apps/:id
/deployments/:id
/settings
```

## App Detail Page Tabs

```text
Overview
Deployments
Logs
Settings
```

Later:

```text
Environment
Metrics
Alerts
```

---

# 20. First Demo Scenario

The first working demo should be based on a realistic app.

Example:

```text
Server: Main VPS
App: Watchdog
Path: /opt/watchdog
Service: watchdog
Branch: main
Deploy command:
  set -e
  git pull origin main
  source .venv/bin/activate
  pip install -r requirements.txt
  alembic upgrade head
  sudo systemctl restart watchdog
```

The demo should show:

1. App registered.
2. Deploy clicked.
3. Logs streaming.
4. Deployment saved.
5. Service restart visible.
6. History updated.

---

# 21. Agent Behavior Rules

The coding agent must follow these rules:

1. Do not build beyond the current milestone.
2. Do not introduce large unrequested features.
3. Do not rewrite unrelated code.
4. Do not skip tests.
5. Do not hide important failures.
6. Do not continue to the next milestone without user approval.
7. Do not store secrets in code.
8. Do not return private keys in API responses.
9. Do not make architecture overly complex.
10. Do not use Docker/Kubernetes unless requested for that milestone.
11. Do not introduce Celery/Redis before it is needed.
12. Do not use root SSH as the default recommendation.
13. Do not create fake passing tests that do not verify behavior.
14. Do not hardcode user-specific paths except in examples.
15. Do not assume the frontend exists before its milestone.

---

# 22. Milestone Completion Response Format

At the end of every milestone, respond using this format:

```markdown
## Milestone X Complete — <Milestone Name>

### What was built

- ...

### Files changed

- `path/to/file`
- `path/to/file`

### How to run it

```bash
...
```

### How to test it

```bash
...
```

### Important design decisions

- ...

### What you should study before continuing

- ...

### Known limitations

- ...

### Next milestone

Milestone X+1 is: <name>

Please review this milestone before we continue.
```

Do not proceed until the user says to continue.

---

# 23. Development Quality Bar

The code should meet this bar:

- Runs locally.
- Tests pass.
- Clear folder structure.
- No obvious security leaks.
- No private keys exposed.
- No broken migrations.
- No dead routes.
- No unused giant abstractions.
- Good error handling.
- Easy to read.
- Easy to extend.

---

# 24. Initial Implementation Instruction

When starting the project, begin with Milestone 0 only.

Do not create all models, auth, SSH, deployment runner, and frontend pages immediately.

Start with:

- repository structure
- FastAPI health endpoint
- React/Vite shell
- config
- database session placeholder
- Alembic setup
- first passing test
- README with local setup

Then stop.

The user must study the code before approving Milestone 1.

---

# 25. Final Reminder

DeployDock should be built like a real product, but in small understandable steps.

The priority order is:

```text
Correctness
Security
Clarity
Learning value
Usefulness
Polish
Scale
```

Do not optimize for scale before the MVP is understandable and working.

