# DeployDock v2
## Self-Hosted VPS Deployment & Management Platform

**Project:** DeployDock  
**Version:** 2.0  
**Status:** Architecture & Development Specification  
**Approach:** Evolve existing DeployDock rather than rewrite from scratch  
**Backend / Control Plane:** Python + FastAPI  
**Infrastructure / Execution Layer:** Go  
**CLI:** Go  
**VPS Agent:** Go  
**Frontend:** Existing React-based dashboard  
**Database:** PostgreSQL  
**Primary Deployment Runtime:** Docker  
**Target Infrastructure:** Linux VPS

---

# 1. IMPORTANT IMPLEMENTATION DIRECTIVE

This project is an **evolution of the existing DeployDock codebase**.

Do **NOT** create an entirely new project from scratch.

The existing DeployDock implementation should be audited, preserved where appropriate, refactored where necessary, and extended according to this specification.

The architecture is intentionally hybrid:

```text
                    DEPLOYDOCK
                         │
            ┌────────────┴────────────┐
            │                         │
            ▼                         ▼
      FASTAPI / PYTHON              GO
       CONTROL PLANE          EXECUTION PLATFORM
            │                         │
            │                         ├── CLI
            │                         ├── VPS Agent
            │                         ├── Deployment execution
            │                         ├── Docker operations
            │                         ├── Nginx operations
            │                         ├── Health checks
            │                         └── System operations
            │
            ├── Authentication
            ├── Dashboard API
            ├── Projects
            ├── Servers
            ├── Deployments
            ├── Environments
            ├── Domains
            ├── Users
            ├── Webhooks
            └── Deployment orchestration
```

### Core architectural principle

> **FastAPI decides what should happen. Go makes it happen.**

Do not rewrite working FastAPI functionality simply to introduce Go.

Go should be introduced where it provides meaningful benefits:

- infrastructure operations
- long-running processes
- CLI tooling
- VPS agent
- deployment execution
- system-level operations
- resource monitoring
- efficient concurrent workloads

---

# 2. PRODUCT VISION

DeployDock is a self-hosted deployment and VPS management platform.

It provides the simplicity of platforms such as Render, Railway, Heroku, and similar PaaS products while allowing the developer to retain ownership of their infrastructure.

The user owns the VPS.

DeployDock manages the VPS.

The desired experience is:

```text
Git Push
   ↓
DeployDock
   ↓
Build
   ↓
Deploy
   ↓
Health Check
   ↓
HTTPS
   ↓
Application Online
```

Instead of manually performing:

```text
SSH into VPS
git pull
install dependencies
build application
configure process
configure Nginx
configure SSL
restart application
check logs
```

DeployDock should automate these operations.

---

# 3. PRODUCT POSITIONING

DeployDock sits between:

```text
Manual VPS Management
        │
        ▼
     DEPLOYDOCK
        │
        ▼
Traditional PaaS
```

Traditional PaaS:

```text
Developer
   ↓
Their infrastructure
```

DeployDock:

```text
Developer
   ↓
Their VPS
   ↓
DeployDock management layer
```

Core proposition:

> **Your infrastructure. Your VPS. Your applications. Deployment simplicity.**

---

# 4. PRIMARY COMPONENTS

DeployDock consists of three major software components.

## 4.1 FastAPI Control Plane

The existing FastAPI backend remains the central control plane.

Responsibilities:

- authentication
- authorization
- users
- projects
- applications
- servers
- environments
- domains
- deployment records
- deployment orchestration
- deployment history
- audit logs
- GitHub webhooks
- API
- dashboard backend
- agent registration
- agent coordination
- desired deployment state

Binary/process:

```text
FastAPI application
```

The existing FastAPI backend should be retained and improved rather than rewritten.

---

# 4.2 DeployDock CLI

A Go command-line application.

Binary:

```bash
deploydock
```

The CLI is intended primarily for developers.

Example:

```bash
deploydock login
deploydock projects
deploydock deploy
deploydock status
deploydock logs
deploydock rollback
```

The CLI should communicate with the FastAPI control plane through its API.

The CLI should NOT normally SSH directly into VPS infrastructure.

Architecture:

```text
deploydock CLI
      ↓
FastAPI API
      ↓
Go Agent
      ↓
VPS
```

---

# 4.3 DeployDock Agent

A lightweight Go daemon installed on managed VPS infrastructure.

Binary:

```bash
deploydock-agent
```

Responsibilities:

- VPS registration
- secure communication
- heartbeat
- Docker management
- container lifecycle
- deployment execution
- health checks
- Nginx management
- filesystem operations
- system information
- application logs
- resource monitoring
- deployment state reporting
- rollback execution
- agent self-updates

The agent runs as a systemd service.

Example:

```text
/etc/systemd/system/deploydock-agent.service
```

---

# 5. FINAL ARCHITECTURE

```text
                         ┌──────────────────────┐
                         │      Developer       │
                         └──────────┬───────────┘
                                    │
                      ┌─────────────┴─────────────┐
                      │                           │
                      ▼                           ▼
              ┌──────────────┐             ┌──────────────┐
              │ Web Dashboard│             │ Go CLI       │
              │ React        │             │ deploydock   │
              └──────┬───────┘             └──────┬───────┘
                     │                            │
                     └────────────┬───────────────┘
                                  ▼
                      ┌────────────────────────┐
                      │   FastAPI Control Plane │
                      │        Python           │
                      ├────────────────────────┤
                      │ Authentication          │
                      │ Projects                │
                      │ Deployments             │
                      │ Servers                 │
                      │ Environments            │
                      │ Domains                 │
                      │ Webhooks                │
                      │ Audit Logs              │
                      │ API                     │
                      └────────────┬───────────┘
                                   │
                            Agent Protocol
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
       ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
       │ VPS #1      │      │ VPS #2      │      │ VPS #3      │
       │ Go Agent    │      │ Go Agent    │      │ Go Agent    │
       ├─────────────┤      ├─────────────┤      ├─────────────┤
       │ Docker      │      │ Docker      │      │ Docker      │
       │ Nginx       │      │ Nginx       │      │ Nginx       │
       │ Applications│      │ Applications│      │ Applications│
       │ System      │      │ System      │      │ System      │
       └─────────────┘      └─────────────┘      └─────────────┘
```

---

# 6. RESPONSIBILITY BOUNDARIES

This boundary must remain clear.

## FastAPI owns

```text
Users
Authentication
Authorization
Projects
Applications
Repositories
Servers
Environments
Domains
Deployments
Deployment history
Audit logs
Webhooks
Configuration
Desired state
API
Dashboard
```

## Go owns

```text
CLI
VPS Agent
Docker
Containers
Nginx
Filesystem
Processes
Health checks
Resource monitoring
Deployment execution
Application logs
Server operations
Rollback execution
```

---

# 7. IMPORTANT: DO NOT CREATE A GO CONTROL PLANE

The previous architecture proposed a Go `deploydock-server`.

That is **not part of the current architecture**.

The final architecture is:

```text
FastAPI
   = Control Plane

Go CLI
   = Developer Interface

Go Agent
   = Infrastructure Execution Layer
```

There is no requirement to rewrite the existing FastAPI control plane in Go.

---

# 8. EXISTING CODEBASE MIGRATION STRATEGY

The project should evolve incrementally.

Do not immediately delete existing deployment functionality.

Migration process:

```text
Existing DeployDock
        ↓
Audit
        ↓
Identify responsibilities
        ↓
Define FastAPI/Go boundaries
        ↓
Build Go Agent
        ↓
Connect Agent to existing API
        ↓
Move infrastructure operations to Agent
        ↓
Build CLI
        ↓
Improve dashboard
        ↓
Add advanced deployment features
```

---

# 9. CODEBASE AUDIT — FIRST DEVELOPMENT TASK

Before major implementation begins, inspect the existing DeployDock repository.

Identify:

```text
FastAPI application
Database models
API routes
Authentication
Deployment services
SSH implementation
Docker implementation
Nginx implementation
Server management
Frontend
Configuration
Environment variables
Background jobs
Deployment logs
Existing tests
Docker configuration
CI/CD
```

Produce a migration matrix:

| Existing Component | Current Technology | Keep | Refactor | Move to Go | Replace |
|---|---|---:|---:|---:|---:|
| Authentication | FastAPI | ✓ | | | |
| Dashboard API | FastAPI | ✓ | | | |
| Projects | FastAPI | ✓ | | | |
| Deployment records | PostgreSQL/FastAPI | ✓ | | | |
| SSH operations | Python | | | ✓ | |
| Docker operations | Python | | | ✓ | |
| Nginx operations | Python | | | ✓ | |
| CLI | Existing | | ✓ | ✓ | |
| VPS agent | None/Existing | | | ✓ | |

The exact matrix must be determined after inspecting the actual repository.

---

# 10. DATABASE

PostgreSQL remains the primary persistent database.

Potential entities:

```text
users
projects
applications
repositories
servers
agents
environments
deployments
deployment_logs
deployment_artifacts
domains
environment_variables
webhooks
audit_logs
```

FastAPI owns the database schema.

The Go agent should not directly manipulate control-plane database tables.

Preferred flow:

```text
Go Agent
   ↓
Agent API
   ↓
FastAPI
   ↓
PostgreSQL
```

This prevents the Go agent from becoming tightly coupled to internal database implementation details.

---

# 11. PROJECT MODEL

A project represents an application managed by DeployDock.

Example:

```text
Project
 ├── Repository
 ├── Branch
 ├── Runtime
 ├── Environment
 ├── Server
 ├── Domain
 ├── Environment Variables
 └── Deployments
```

Example:

```text
watchdog
 ├── GitHub repository
 ├── main
 ├── Docker
 ├── Production
 ├── production VPS
 ├── watchdog.example.com
 └── Deployment #43
```

---

# 12. ENVIRONMENTS

Projects can have multiple environments.

Initial environments:

```text
Production
Staging
Development
```

Each environment may have:

```text
Server
Domain
Environment variables
Deployment configuration
Resources
```

Example:

```text
watchdog
 ├── Production
 │    ├── Production VPS
 │    └── watchdog.example.com
 │
 └── Staging
      ├── Staging VPS
      └── staging.watchdog.example.com
```

---

# 13. DEPLOYMENT MODEL

Deployments are first-class resources.

Example:

```text
Deployment #43

Project: watchdog
Environment: production
Commit: a81f92c
Status: SUCCESS
Started: ...
Finished: ...
```

Deployment states:

```text
PENDING
QUEUED
CLONING
BUILDING
TESTING
DEPLOYING
HEALTH_CHECK
SUCCESS
FAILED
CANCELLED
ROLLED_BACK
```

---

# 14. DEPLOYMENT PIPELINE

Standard deployment:

```text
1. Create deployment
2. Queue deployment
3. Resolve Git commit
4. Clone repository
5. Build Docker image
6. Run tests
7. Create new container
8. Start container
9. Health check
10. Configure/update Nginx
11. Switch traffic
12. Mark deployment successful
13. Preserve previous version
14. Cleanup old resources
```

---

# 15. DEPLOYMENT RESPONSIBILITY

FastAPI:

```text
Create deployment
Validate configuration
Queue deployment
Tell agent what to deploy
Track state
Store events
Expose logs
```

Go Agent:

```text
Clone
Build
Test
Create container
Start container
Health check
Configure infrastructure
Switch traffic
Cleanup
Report result
```

This distinction is critical.

---

# 16. DEPLOYMENT ENGINE

The Go agent should contain a modular deployment engine.

Conceptually:

```go
type DeploymentEngine interface {
    Deploy(ctx context.Context, request DeploymentRequest) error
    Rollback(ctx context.Context, request RollbackRequest) error
}
```

Stages:

```text
CloneStage
BuildStage
TestStage
StartStage
HealthCheckStage
ProxyStage
CleanupStage
```

Each stage should have a clear responsibility.

---

# 17. ZERO-DOWNTIME DEPLOYMENTS

DeployDock should avoid:

```text
STOP OLD
START NEW
```

Preferred:

```text
             Nginx
               │
               ▼
        Application v41
               │
          Deploy v42
               │
               ▼
        Application v42
               │
          Health check
               │
             PASS
               │
               ▼
             Nginx
               │
               ▼
        Application v42
```

The old application remains available until the new application passes health checks.

---

# 18. HEALTH CHECKS

Initial support:

```text
HTTP
```

Example:

```yaml
health:
  type: http
  path: /health
  expected_status: 200
  timeout: 5s
  retries: 5
```

Future:

```text
TCP
Command
Custom checks
```

A deployment must not become active if its health checks fail.

---

# 19. ROLLBACK

Every successful deployment should remain a rollback candidate.

Example:

```text
#43 a81f92c CURRENT
#42 92bc112
#41 7ad91fa
#40 81b20aa
```

CLI:

```bash
deploydock rollback
```

Specific deployment:

```bash
deploydock rollback --to 42
```

Rollback should generate a new deployment event.

Example:

```text
#43 successful
#44 rollback to #42
```

History must remain immutable.

---

# 20. DEPLOYMENT LOGGING

Deployment logs must be streamed from the Go agent through the control plane.

Flow:

```text
Go Agent
   ↓
Deployment events
   ↓
FastAPI
   ↓
PostgreSQL / event stream
   ↓
Dashboard / CLI
```

Example:

```text
✓ Resolving commit
✓ Cloning repository
✓ Building Docker image
✓ Running tests
✓ Starting container
✓ Health check passed
✓ Updating Nginx
✓ Deployment successful
```

CLI:

```bash
deploydock logs
```

Follow mode:

```bash
deploydock logs --follow
```

---

# 21. VPS AGENT

The agent is a Go daemon.

Binary:

```bash
deploydock-agent
```

Responsibilities:

```text
Registration
Authentication
Heartbeat
System information
Docker
Containers
Images
Nginx
Filesystem
Health checks
Logs
Deployment execution
Rollback
Resource monitoring
```

---

# 22. AGENT INSTALLATION

Installation should be simple.

Example:

```bash
curl -fsSL https://get.deploydock.dev | sh
```

Then:

```bash
sudo deploydock-agent install
```

Registration:

```bash
sudo deploydock-agent register \
  --token <registration-token>
```

The installer should eventually support:

```text
Linux amd64
Linux arm64
Linux armv7
```

---

# 23. AGENT SERVICE

The agent runs through systemd.

Example:

```text
/etc/systemd/system/deploydock-agent.service
```

Expected commands:

```bash
sudo systemctl status deploydock-agent
sudo systemctl restart deploydock-agent
sudo systemctl enable deploydock-agent
```

Agent CLI:

```bash
deploydock-agent status
deploydock-agent version
deploydock-agent doctor
deploydock-agent register
deploydock-agent upgrade
```

---

# 24. AGENT SECURITY

Requirements:

- encrypted communication
- authenticated agent
- short-lived registration tokens
- server identity
- token rotation
- least privilege
- no plaintext secrets in logs
- signed requests where appropriate
- replay protection
- secure credential storage

The agent must never blindly execute arbitrary commands received from an untrusted source.

---

# 25. AGENT COMMUNICATION

Initial protocol:

```text
HTTPS
```

Possible future protocol:

```text
gRPC
```

The agent should preferably establish an outbound connection to the control plane.

This avoids requiring users to expose a management port to the internet.

Conceptual flow:

```text
VPS Agent
    │
    │ outbound connection
    ▼
FastAPI
```

Commands:

```text
DEPLOY
ROLLBACK
GET_STATUS
GET_LOGS
HEALTH_CHECK
RESTART
```

Events:

```text
DEPLOYMENT_STARTED
STAGE_STARTED
LOG
STAGE_COMPLETED
HEALTH_CHECK_PASSED
HEALTH_CHECK_FAILED
DEPLOYMENT_COMPLETED
DEPLOYMENT_FAILED
```

---

# 26. AGENT HEARTBEAT

The agent periodically reports:

```text
Agent version
Server identity
CPU
Memory
Disk
Container status
Application status
Last deployment
```

Example:

```text
Production VPS

Agent: v2.0.0
Status: ONLINE
CPU: 21%
Memory: 43%
Disk: 38%
Last heartbeat: 5 seconds ago
```

If the agent becomes unavailable:

```text
Server: OFFLINE
```

Existing applications should continue running.

DeployDock should not automatically terminate running applications because the control plane cannot communicate with the agent.

---

# 27. STATE SYNCHRONIZATION

The control plane maintains desired state.

The agent reports actual state.

Conceptually:

```text
Desired State
      ↓
FastAPI
      ↓
Go Agent
      ↓
Actual State
```

Future architecture:

```text
Desired State
      ↓
Reconciliation
      ↓
Agent
      ↓
Actual State
```

This should eventually enable declarative infrastructure.

---

# 28. GO CLI

Binary:

```bash
deploydock
```

The CLI should communicate with FastAPI.

It should not directly manipulate PostgreSQL.

---

# 29. CLI COMMANDS

## Authentication

```bash
deploydock login
deploydock logout
deploydock whoami
```

## Projects

```bash
deploydock projects
deploydock project create
deploydock project inspect
deploydock project delete
```

## Initialization

```bash
deploydock init
```

## Deployment

```bash
deploydock deploy
deploydock deploy watchdog
deploydock deploy --env production
```

## Status

```bash
deploydock status
```

## Logs

```bash
deploydock logs
deploydock logs --follow
deploydock logs --deployment 43
```

## Rollback

```bash
deploydock rollback
deploydock rollback --to 42
```

## Environment

```bash
deploydock env list
deploydock env set API_KEY=value
deploydock env unset API_KEY
```

## Servers

```bash
deploydock servers
deploydock server inspect
```

---

# 30. CLI UX

The CLI should feel polished and developer-friendly.

Example:

```text
$ deploydock deploy

Deploying watchdog...

✓ Resolving repository
✓ Commit a81f92c
✓ Building image
✓ Running tests
✓ Starting container
✓ Health check passed
✓ Updating Nginx
✓ Deployment successful

Deployment #43

https://watchdog.example.com
```

Human-readable output should be the default.

Machine-readable output:

```bash
deploydock status --json
```

---

# 31. CLI CONFIGURATION

Configuration:

```text
~/.config/deploydock/config.yaml
```

Example:

```yaml
api_url: https://deploydock.example.com
```

Authentication credentials should be stored securely.

Multiple contexts should eventually be supported:

```bash
deploydock context production
deploydock context staging
```

---

# 32. PROJECT INITIALIZATION

The CLI should inspect the project.

Example:

```bash
deploydock init
```

Possible detection:

```text
Language: Go
Dockerfile: Found
Port: 8080
Git repository: Found
```

Then generate:

```text
deploydock.yaml
```

Example:

```yaml
name: watchdog

build:
  type: docker
  dockerfile: Dockerfile

deploy:
  port: 8080

health:
  path: /health
```

---

# 33. RUNTIME SUPPORT

Initial runtime:

```text
Docker
```

Future:

```text
Go
Python
Node.js
Static
Docker Compose
```

Docker should remain the primary runtime because it provides predictable environments.

---

# 34. DOCKER MANAGEMENT

The Go agent manages Docker.

Capabilities:

```text
Build image
Pull image
Create container
Start container
Stop container
Restart container
Remove container
Inspect container
Stream logs
Apply resource limits
```

Docker operations must be abstracted behind interfaces so they can be tested.

---

# 35. NGINX MANAGEMENT

The Go agent manages Nginx configuration.

Flow:

```text
Application
     ↓
Go Agent
     ↓
Generate configuration
     ↓
Validate Nginx config
     ↓
Reload Nginx
```

DeployDock must avoid unnecessarily modifying unrelated Nginx configurations.

Managed configuration should be clearly separated from user-managed configuration.

---

# 36. DOMAINS

Users can attach domains to applications.

Example:

```text
watchdog.example.com
```

Workflow:

```text
Add domain
    ↓
DNS verification
    ↓
Nginx configuration
    ↓
SSL certificate
    ↓
HTTPS
```

---

# 37. SSL

DeployDock should eventually automate HTTPS using Let's Encrypt.

Requirements:

- certificate provisioning
- renewal
- expiration monitoring
- Nginx integration
- failure reporting

---

# 38. ENVIRONMENT VARIABLES

Example:

```text
DATABASE_URL
SECRET_KEY
REDIS_URL
API_KEY
```

Environment variables belong to environments.

Example:

```text
Production:
DATABASE_URL=...
DEBUG=false

Staging:
DATABASE_URL=...
DEBUG=true
```

Secrets must be:

- encrypted at rest
- masked in UI
- masked in CLI
- excluded from logs
- access controlled

---

# 39. GITHUB INTEGRATION

Initial Git provider:

```text
GitHub
```

Future:

```text
GitLab
Bitbucket
Generic Git
```

Repository metadata:

```text
repository URL
provider
branch
deployment trigger
```

---

# 40. GITHUB WEBHOOKS

Flow:

```text
git push
   ↓
GitHub
   ↓
Webhook
   ↓
FastAPI
   ↓
Deployment
   ↓
Go Agent
```

Webhook security:

- signature verification
- replay protection
- repository validation
- branch validation

---

# 41. AUTOMATIC DEPLOYMENTS

Project configuration:

```text
Automatic Deployments: ON
```

Then:

```text
git push main
      ↓
GitHub
      ↓
DeployDock
      ↓
Deployment
```

Users must be able to disable automatic deployments.

---

# 42. DEPLOYMENT QUEUE

Deployments should be queued.

Example:

```text
#44 RUNNING
#45 QUEUED
#46 QUEUED
```

Initial rule:

```text
One active deployment per environment.
```

This prevents concurrent production deployments from corrupting application state.

---

# 43. AUDIT LOGGING

Important events must be recorded.

Examples:

```text
User logged in
Project created
Server registered
Deployment started
Deployment succeeded
Deployment failed
Rollback executed
Environment variable changed
Domain added
Agent registered
```

Audit logs should be immutable.

---

# 44. AUTHENTICATION

Existing authentication should be retained where it is secure.

Potential future methods:

```text
Email/password
GitHub OAuth
Google OAuth
Passkeys
2FA
```

Passwords must use secure password hashing.

Sessions/tokens must support revocation.

---

# 45. AUTHORIZATION

Initial roles:

```text
Owner
Admin
Member
Viewer
```

Example:

```text
Owner
  Everything

Admin
  Manage servers
  Manage projects
  Deploy

Member
  Deploy
  View logs

Viewer
  Read-only
```

---

# 46. API

FastAPI remains the primary API.

Base path:

```text
/api/v1
```

Example endpoints:

```text
POST   /api/v1/auth/login

GET    /api/v1/projects
POST   /api/v1/projects
GET    /api/v1/projects/{id}
DELETE /api/v1/projects/{id}

GET    /api/v1/projects/{id}/deployments
POST   /api/v1/projects/{id}/deployments

GET    /api/v1/deployments/{id}
POST   /api/v1/deployments/{id}/cancel
POST   /api/v1/deployments/{id}/rollback

GET    /api/v1/servers
POST   /api/v1/servers

GET    /api/v1/domains
POST   /api/v1/domains
```

Agent-specific APIs should be separated logically.

Example:

```text
/api/v1/agents
/api/v1/agents/{id}/heartbeat
/api/v1/agents/{id}/events
/api/v1/agents/{id}/commands
```

Exact API design should be finalized after auditing the existing API.

---

# 47. LIVE EVENTS

Initial implementation should use SSE where appropriate.

Example:

```text
GET /api/v1/deployments/{id}/events
```

Events:

```text
deployment.started
deployment.stage_started
deployment.log
deployment.stage_completed
deployment.failed
deployment.completed
```

WebSockets may be introduced later where bidirectional communication provides a clear advantage.

---

# 48. OBSERVABILITY

DeployDock should expose:

```text
/health
/ready
/metrics
```

Metrics:

```text
deployment_total
deployment_success_total
deployment_failure_total
deployment_duration_seconds
agent_online_total
agent_heartbeat_age
```

The agent should also report system metrics.

---

# 49. ERROR MODEL

Deployment failures should be categorized.

Examples:

```text
GIT_ERROR
BUILD_ERROR
TEST_ERROR
CONTAINER_ERROR
HEALTH_CHECK_ERROR
NETWORK_ERROR
NGINX_ERROR
CERTIFICATE_ERROR
AGENT_ERROR
TIMEOUT
```

The dashboard should provide human-readable explanations.

Raw stack traces should not be the primary user-facing error.

---

# 50. RESOURCE LIMITS

Applications should eventually support:

```yaml
resources:
  cpu: 1
  memory: 512Mi
```

The Go agent should apply Docker resource limits.

This prevents one application from consuming the entire VPS.

---

# 51. NETWORKING

Applications should ideally run behind Nginx.

Architecture:

```text
Internet
   ↓
Nginx
   ↓
Docker network
   ↓
Application
```

Application containers should not necessarily expose ports directly to the public internet.

---

# 52. DATABASE SUPPORT

Managed databases are explicitly **not part of the MVP**.

Future support:

```text
PostgreSQL
Redis
MySQL
```

Potential model:

```text
Project
 ├── Application
 ├── PostgreSQL
 └── Redis
```

---

# 53. BACKUPS

Future feature.

Potential capabilities:

```text
Database backups
Volume backups
Configuration backups
Deployment metadata backups
```

Scheduling:

```text
Daily
Weekly
Custom
```

---

# 54. NOTIFICATIONS

Future integrations:

```text
Discord
Slack
Telegram
Email
Generic Webhook
```

Example:

```text
✓ Deployment successful

Project: watchdog
Deployment: #43
Commit: a81f92c
Duration: 41s
```

---

# 55. DEPLOYMENT STRATEGIES

Initial strategy:

```text
Blue-Green style single-host deployment
```

Future:

```text
Rolling
Blue-Green
Canary
Recreate
```

---

# 56. MULTI-SERVER DEPLOYMENTS

Future:

```text
                 Load Balancer
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
        VPS #1      VPS #2      VPS #3
```

This should be added only after single-server deployments are stable.

---

# 57. DECLARATIVE INFRASTRUCTURE

Long-term DeployDock should support desired state.

Example:

```yaml
application:
  name: watchdog

image:
  repository: watchdog
  tag: a81f92c

replicas: 1

domain:
  - watchdog.example.com

health:
  path: /health
```

Architecture:

```text
deploydock.yaml
      ↓
Desired State
      ↓
FastAPI
      ↓
Go Agent
      ↓
Actual State
```

Future reconciliation:

```text
Desired State
      ↓
Compare
      ↓
Actual State
      ↓
Apply changes
```

---

# 58. GO PROJECT STRUCTURE

The Go components should be organized independently from the FastAPI application.

Recommended:

```text
deploydock/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── auth/
│   │   ├── projects/
│   │   ├── deployments/
│   │   ├── servers/
│   │   ├── environments/
│   │   ├── domains/
│   │   ├── agents/
│   │   └── webhooks/
│   │
│   └── migrations/
│
├── frontend/
│
├── go/
│   ├── cmd/
│   │   ├── deploydock/
│   │   │   └── main.go
│   │   │
│   │   └── deploydock-agent/
│   │       └── main.go
│   │
│   ├── internal/
│   │   ├── agent/
│   │   ├── deployment/
│   │   ├── docker/
│   │   ├── nginx/
│   │   ├── health/
│   │   ├── system/
│   │   ├── git/
│   │   └── client/
│   │
│   └── go.mod
│
├── deploydock.yaml
├── docker-compose.yml
├── Makefile
└── README.md
```

The exact structure can change after inspecting the current repository.

---

# 59. GO LIBRARY DESIGN

Infrastructure dependencies should use interfaces.

Example:

```go
type ContainerRuntime interface {
    Build(ctx context.Context, image string, path string) error
    Start(ctx context.Context, config ContainerConfig) error
    Stop(ctx context.Context, id string) error
    Logs(ctx context.Context, id string) (io.ReadCloser, error)
}
```

Similarly:

```go
type HealthChecker interface {
    Check(ctx context.Context, target HealthTarget) error
}
```

And:

```go
type ProxyManager interface {
    Configure(ctx context.Context, config ProxyConfig) error
    Validate(ctx context.Context) error
    Reload(ctx context.Context) error
}
```

This makes the infrastructure layer testable.

---

# 60. TECHNOLOGY STACK

## Existing / Control Plane

```text
Python
FastAPI
PostgreSQL
```

## Frontend

```text
React
TypeScript
Vite
Tailwind CSS
```

## Go

```text
Go
Cobra
pgx only where direct database access is genuinely required
Go slog
standard library where practical
```

Avoid unnecessary dependencies.

---

# 61. TESTING STRATEGY

## FastAPI

Test:

```text
Authentication
Authorization
API endpoints
Database operations
Deployment state transitions
Agent API
Webhook verification
```

## Go

Test:

```text
CLI
Agent
Docker abstraction
Deployment stages
Health checks
Nginx configuration
Rollback
Agent communication
```

## Integration tests

```text
FastAPI → PostgreSQL
FastAPI → Agent
Agent → Docker
Deployment → Health check
CLI → FastAPI
```

## End-to-end

```text
Create project
     ↓
Register VPS
     ↓
Connect repository
     ↓
Deploy
     ↓
Health check
     ↓
HTTPS
     ↓
Deploy new version
     ↓
Rollback
```

---

# 62. LOCAL DEVELOPMENT

The project should be easy to run locally.

Example:

```bash
docker compose up
```

Services may include:

```text
FastAPI
PostgreSQL
Frontend
Mock Agent
```

Redis should only be introduced when its use is justified.

---

# 63. CI/CD

GitHub Actions should run:

```text
format
lint
unit tests
integration tests
build
security checks
Docker build
```

Go:

```text
go test ./...
go vet ./...
```

Python:

```text
pytest
ruff
```

Frontend:

```text
lint
build
test
```

---

# 64. RELEASES

The release process should produce:

```text
deploydock-linux-amd64
deploydock-linux-arm64

deploydock-agent-linux-amd64
deploydock-agent-linux-arm64
```

Future packages:

```text
.deb
.rpm
.tar.gz
Homebrew
```

Versioning:

```text
v2.0.0
v2.1.0
v2.1.1
```

---

# 65. AGENT UPDATES

Future:

```bash
deploydock agent upgrade
```

Upgrade process:

```text
New version
    ↓
Download
    ↓
Verify checksum/signature
    ↓
Replace binary
    ↓
Restart agent
    ↓
Health check
```

An unsuccessful upgrade must not leave the server without a functioning agent.

---

# 66. MVP

The MVP should be deliberately focused.

## FastAPI

```text
Authentication
Projects
Servers
Environments
Deployments
Deployment history
Agent registration
```

## Go Agent

```text
Registration
Heartbeat
Docker
Deployment execution
Health checks
Logs
Basic Nginx integration
```

## Go CLI

```text
login
projects
deploy
status
logs
rollback
```

## Infrastructure

```text
Docker
Nginx
HTTPS
PostgreSQL
```

---

# 67. DEVELOPMENT PHASE 0 — AUDIT

Before writing major new code:

1. Read the existing repository.
2. Understand current architecture.
3. Identify current deployment workflow.
4. Identify current database models.
5. Identify current APIs.
6. Identify current SSH functionality.
7. Identify current Docker functionality.
8. Identify current Nginx functionality.
9. Identify frontend capabilities.
10. Identify existing tests.
11. Identify technical debt.
12. Produce migration plan.

**No major rewrite should happen before this audit.**

---

# 68. DEVELOPMENT PHASE 1 — ARCHITECTURAL BOUNDARY

Define:

```text
FastAPI responsibilities
Go responsibilities
Agent protocol
CLI API usage
Database ownership
Deployment event model
```

Deliverable:

```text
Stable FastAPI ↔ Agent contract
```

---

# 69. DEVELOPMENT PHASE 2 — GO AGENT

Build:

```text
Agent binary
Configuration
Registration
Authentication
Heartbeat
System information
Docker abstraction
```

Deliverable:

```text
A real VPS can register with DeployDock.
```

---

# 70. DEVELOPMENT PHASE 3 — DEPLOYMENT ENGINE

Move infrastructure execution into Go.

Build:

```text
Clone
Build
Test
Start
Health check
Logs
Stop
Rollback
```

Deliverable:

```text
FastAPI creates deployment
        ↓
Go Agent executes deployment
        ↓
FastAPI records result
```

---

# 71. DEVELOPMENT PHASE 4 — CLI

Build:

```bash
deploydock login
deploydock projects
deploydock deploy
deploydock status
deploydock logs
deploydock rollback
```

Deliverable:

```text
A developer can operate DeployDock without opening the dashboard.
```

---

# 72. DEVELOPMENT PHASE 5 — PRODUCTION FEATURES

Build:

```text
Zero-downtime deployment
Nginx automation
Domains
SSL
Environment variables
Secrets
Deployment locking
```

---

# 73. DEVELOPMENT PHASE 6 — GITHUB AUTOMATION

Build:

```text
GitHub integration
Webhooks
Automatic deployments
Commit metadata
Deployment status
```

Deliverable:

```text
git push
   ↓
automatic deployment
```

---

# 74. DEVELOPMENT PHASE 7 — RELIABILITY

Build:

```text
Retries
Deployment queue
Agent reconnection
State synchronization
Rollback improvements
Resource limits
Agent upgrades
```

---

# 75. DEVELOPMENT PHASE 8 — ADVANCED PLATFORM

Future:

```text
Multi-server deployments
Multiple replicas
Canary deployments
Blue-green deployments
Load balancing
Managed databases
Backups
Notifications
Teams
RBAC
```

---

# 76. NON-GOALS

Do not initially build:

```text
Kubernetes
Cloud provisioning
Managed databases
Multi-region infrastructure
Service mesh
Complex orchestration
Autoscaling
Billing
Marketplace
```

The first objective is:

> **Make deploying and managing applications on Linux VPS infrastructure extremely reliable and simple.**

---

# 77. SUCCESS CRITERIA

DeployDock v2 MVP is successful when a developer can:

1. Log into DeployDock.
2. Register a VPS.
3. Install the Go agent.
4. Connect a Git repository.
5. Create an application.
6. Configure environment variables.
7. Deploy the application.
8. Access the application over HTTPS.
9. View live deployment logs.
10. Push a new commit.
11. Automatically deploy the new version.
12. Detect failed deployments.
13. Roll back.
14. Perform the same operations from the CLI.
15. View VPS health.
16. Manage multiple applications on one VPS.
17. Continue running applications when the control plane is temporarily unavailable.

---

# 78. EXAMPLE COMPLETE WORKFLOW

## Install Agent

```bash
curl -fsSL https://get.deploydock.dev | sh
```

```bash
sudo deploydock-agent register --token ...
```

---

## Initialize Project

```bash
cd watchdog
deploydock init
```

---

## Deploy

```bash
deploydock deploy
```

Expected:

```text
Deploying watchdog...

✓ Resolving repository
✓ Commit a81f92c
✓ Building image
✓ Running tests
✓ Starting container
✓ Health check passed
✓ Updating Nginx
✓ Deployment successful

Deployment #43

https://watchdog.example.com
```

---

## Push New Version

```bash
git push origin main
```

GitHub:

```text
Webhook
   ↓
FastAPI
   ↓
Deployment #44
   ↓
Go Agent
   ↓
Build
   ↓
Health check
   ↓
Success
```

---

## Failure

If deployment #44 fails:

```text
Deployment #44
Status: FAILED
Stage: HEALTH_CHECK

Reason:
HTTP 502 after 5 attempts.

Previous deployment remains active:
#43
```

The application remains available.

---

## Rollback

```bash
deploydock rollback --to 43
```

Expected:

```text
Rolling back watchdog...

✓ Restoring deployment #43
✓ Starting container
✓ Health check passed
✓ Traffic switched

✓ Rollback successful
```

---

# 79. FINAL ARCHITECTURAL PHILOSOPHY

DeployDock should not be treated as three unrelated applications.

It is one platform with three specialized components.

```text
                 DEPLOYDOCK
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
     FastAPI        CLI         Agent
        │            │            │
   Control Plane  Developer    Infrastructure
                  Interface      Execution
```

### FastAPI

**"What should happen?"**

### CLI

**"How does the developer interact with it?"**

### Go Agent

**"How does it actually happen on the VPS?"**

This separation should guide all future architectural decisions.

---

# 80. FINAL PRODUCT GOAL

The mature DeployDock experience should be:

```text
Developer
    │
    │ deploydock deploy
    ▼
FastAPI Control Plane
    │
    │ deployment command
    ▼
Go Agent
    │
    ├── Git
    ├── Docker
    ├── Health Check
    ├── Nginx
    └── System
    │
    ▼
Production Application
```

while the dashboard provides:

```text
Projects
Deployments
Live Logs
Servers
Metrics
Domains
SSL
Environments
Secrets
Deployment History
Rollbacks
```

The ultimate objective is:

> **A developer should be able to run production applications on their own VPS with the convenience of a modern PaaS, without having to manually SSH into the server for routine deployment and management tasks.**

DeployDock should preserve the control and flexibility of VPS infrastructure while providing the developer experience of a modern deployment platform.
