# DeployDock v2 — Master Spec Progress

Tracking file for implementing `DeployDock_v2_Master_Spec.md` linearly, phase by phase.
Every checkbox maps to a concrete deliverable. Update this file as work lands.

Legend: `[x]` done · `[~]` in progress / partially done · `[ ]` not started

---

## Phase 0 — Audit (spec §9, §67) — ✅ COMPLETE

Audit of the existing v1 codebase, produced before any new implementation.

- [x] Read the existing repository (FastAPI app, models, routes, services, frontend, tests, CI)
- [x] Identify current deployment workflow (SSH exec of user-defined commands, in-process background runner)
- [x] Identify current database models (users, servers, apps, deployments, deployment_logs, audit_logs)
- [x] Identify current APIs (`/api/v1`: auth, servers, apps, deployments, dashboard)
- [x] Identify current SSH functionality (asyncssh, host-key pinning, encrypted private keys)
- [x] Docker functionality — **none exists**
- [x] Nginx functionality — **none exists**
- [x] Identify frontend capabilities (dashboard, servers, apps, deployments, live log stream via SSE)
- [x] Identify existing tests (pytest backend suite incl. concurrency/stream/encryption; frontend vitest)
- [x] Identify technical debt / landing-page claims vs. implementation gaps

### Migration matrix (spec §9 deliverable)

| Existing Component | Current Technology | Keep | Refactor | Move to Go | Replace |
|---|---|:-:|:-:|:-:|:-:|
| Authentication (Argon2id + JWT) | FastAPI | ✓ | | | |
| Dashboard API | FastAPI | ✓ | | | |
| Deployment records / history | PostgreSQL/FastAPI | ✓ | | | |
| Audit logs | FastAPI/PostgreSQL | ✓ | | | |
| Deployment SSE log stream | FastAPI | ✓ | (extend with stage events) | | |
| Servers CRUD + host-key pinning | FastAPI | ✓ | (becomes agent host registry) | | |
| SSH execution (ssh_service, runner) | Python/asyncssh | | (bridge during transition) | ✓ | |
| Deployment runner (SSH commands) | Python | | | ✓ (agent engine) | |
| "App" model (flat, commands-only) | FastAPI/PostgreSQL | | ✓ (→ Project/Environments) | | |
| CLI | — | | | ✓ (build new) | |
| VPS agent | — | | | ✓ (build new) | |
| Docker operations | — | | | ✓ (build new) | |
| Nginx operations | — | | | ✓ (build new) | |

### Audit findings (landing page vs. implementation)

Claims with no implementation: agent, CLI (`dock`), git-push webhooks, deploy cancel,
health-check gating, systemd unit generation, release snapshots/symlink rollback,
log filter/search/pin, install script, LICENSE file (footer claims MIT).
Details in conversation log of 2026-09-03; each is covered by a spec phase below.

---

## Phase 1 — Architectural boundary (spec §68) — ✅ COMPLETE

Deliverable: **stable FastAPI ↔ Agent contract**.

- [x] Confirm responsibility boundaries (spec §6): FastAPI owns state, Go owns execution
- [x] Agent protocol v1 defined: endpoints, auth model, command/event schemas → `docs/agent-protocol.md`
- [x] Deployment event model defined (STAGE_STARTED / LOG / STAGE_COMPLETED / …)
- [x] Command model defined (DEPLOY / ROLLBACK / RESTART / GET_STATUS / GET_LOGS / HEALTH_CHECK)
- [x] Database ownership rule recorded (agent never touches PostgreSQL directly)

## Phase 2 — Go agent: registration & heartbeat (spec §21–26, §69)

### 2a. Control plane: agent registration API (FastAPI)

- [x] `agents` table + Alembic migration (`0006_create_agents`)
- [x] Registration-token model (short-lived, single-use, stored hashed)
- [x] `POST /api/v1/agents/registration-tokens` (user auth) — mint token
- [x] `POST /api/v1/agents/register` (registration token) — create agent, issue agent token
- [x] `POST /api/v1/agents/{id}/heartbeat` (agent token) — metrics + liveness
- [x] `GET /api/v1/agents` (user auth) — list agents with online/offline status
- [x] `POST /api/v1/agents/{id}/rotate-token` (user auth) — rotate a compromised agent token
- [x] Audit log entries for register / rotate / heartbeat-timeouts
- [x] Backend tests for the agent API

### 2b. Go agent skeleton

- [x] `go/` module scaffold per spec §58 (cmd/deploydock-agent, internal/*)
- [x] Configuration (env + flags; config file comes with the CLI in phase 4)
- [x] `register` command: exchange registration token for persistent agent token
- [x] `run` command: systemd-friendly foreground loop with outbound heartbeat
- [x] System info collection (hostname, arch, OS, CPU/mem/disk where readable)
- [x] `version` / `doctor` commands
- [x] Go unit tests for pure logic (config, token storage, payload shaping)

## Phase 3 — Deployment engine in agent (spec §13–20, §70)

- [ ] Deployment state machine extended in FastAPI (QUEUED, CLONING, BUILDING, TESTING, DEPLOYING, HEALTH_CHECK, CANCELLED, ROLLED_BACK)
- [ ] `POST /api/v1/deployments/{id}/cancel` (spec §46)
- [ ] Command queue: FastAPI issues DEPLOY/ROLLBACK commands, agent polls/acks
- [ ] Agent streams STAGE_*/LOG events back through the control plane
- [ ] Docker runtime abstraction in agent (build/pull/create/start/stop/logs, interface-driven)
- [ ] Health-check stage (HTTP; expected status, timeout, retries) gating activation
- [ ] Rollback as a new deployment event targeting a previous successful deployment
- [ ] Deployment runner bridge removed once agent path is the default (SSH path kept until then)

## Phase 4 — CLI (spec §28–32, §71)

- [ ] `deploydock login/logout/whoami` (token stored in config dir)
- [ ] `deploydock projects` (+ create/inspect/delete)
- [ ] `deploydock deploy` (human-readable stage output; `--json` machine mode)
- [ ] `deploydock status` / `deploydock logs [--follow] [--deployment N]`
- [ ] `deploydock rollback [--to N]`
- [ ] `deploydock init` → generates `deploydock.yaml`
- [ ] Go tests for CLI against a stub control plane

## Phase 5 — Production features (spec §17–19, §35–38, §55, §72)

- [ ] Zero-downtime deploys (new container live before old stops)
- [ ] Nginx config generation + validation + reload (managed configs separated from user configs)
- [ ] Domains: attach domain → DNS verification → Nginx → SSL
- [ ] SSL via Let's Encrypt (provision, renew, expiry monitoring)
- [ ] Environment variables per environment (encrypted at rest, masked in UI/CLI/logs)
- [ ] Deployment locking per environment

## Phase 6 — GitHub automation (spec §39–41, §73)

- [ ] Webhook endpoint with signature verification + replay protection
- [ ] Repository/branch validation, per-project auto-deploy toggle
- [ ] Commit metadata on deployments

## Phase 7 — Reliability (spec §26–27, §42, §50, §65, §74)

- [ ] Deployment queue (one active per environment; QUEUED state)
- [ ] Agent reconnection + state synchronization (desired vs. actual)
- [ ] Resource limits on containers (cpu/memory)
- [ ] Agent self-upgrade (verify → replace → restart → health check, safe on failure)
- [ ] Observability: `/metrics`, deployment + agent metrics

## Phase 8 — Advanced platform (spec §45, §52–56, §75) — NOT STARTED

- [ ] Roles/teams (Owner/Admin/Member/Viewer)
- [ ] Multi-server deployments / load balancing
- [ ] Canary/blue-green strategies beyond single host
- [ ] Managed databases (PostgreSQL/Redis)
- [ ] Backups, notifications

---

## Standing rules (from spec §1, §7, §76)

- Evolve, don't rewrite: FastAPI control plane is permanent; no Go control plane.
- FastAPI decides *what*; agent/CLI decide *how*.
- Never let the agent manipulate PostgreSQL directly — always via the API.
- Non-goals for now: Kubernetes, cloud provisioning, managed DBs, autoscaling, billing.
