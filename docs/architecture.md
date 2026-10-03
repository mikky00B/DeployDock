# Architecture

## Components

```text
Browser (React + Vite)  /  deploydock CLI (Go)
   |  JSON over HTTPS, bearer token
   v
FastAPI backend  ----  PostgreSQL (users, servers, apps, deployments, logs,
   |                \   agents, commands, environments, variables, domains,
   |                 \  webhook deliveries, audit)
   |                 --  Redis (optional: rate limiting)
   |
   |-- path A: SSH bridge  -- on-demand SSH, host key verified --> your app
   |
   |-- path B: command queue -- poll -- Go agent (outbound HTTPS only) --> Docker
```

There are two execution paths for a deployment, and which one runs is decided
per deployment: if the app's server has a registered agent, the deployment is
enqueued as a self-contained command the agent claims; otherwise it falls back
to the SSH bridge runner. Both paths feed the same deployment records, SSE log
stream, and audit trail.

- **Path A (SSH bridge).** The backend opens an SSH connection when it has
  something to do, runs your command, streams the output, and closes. Nothing
  is installed on the target server.
- **Path B (agent).** The Go agent (`deploydock-agent`) registers against a
  server, sends heartbeats with system metrics, claims queued commands, and
  runs a staged Docker pipeline: clone, build, start the new container, health
  check it, configure nginx, switch traffic, stop the old container. The agent
  only ever makes **outbound** connections — no management port is opened on
  the VPS. Its protocol is documented in [Agent protocol](agent-protocol.md).

## Backend layout

```text
app/
  api/v1/      HTTP routes; thin, mostly translating between HTTP and services
  api/deps.py  auth dependency (bearer -> User)
  core/        config, security, encryption, secrets, rate limiting, logging
  db/          async engine and sessionmaker
  models/      SQLAlchemy models
  schemas/     Pydantic request/response models
  services/    business logic; where the rules live
  workers/     the deployment runner
```

Routes stay thin so behaviour is testable without HTTP. `core/` holds no
business logic and imports nothing from `services/`.

Note one deliberate seam: `core/encryption.py` holds the primitives and knows
nothing about settings, while `core/secrets.py` wraps them with the active key
id and retired-key set. Callers use `core/secrets.py`; nothing else should reach
for the primitives directly.

## Data model

```text
User 1---* Server 1---* App 1---* Deployment 1---* DeploymentLog
User 1---* AuditLog
User 1---* Agent 1---* DeploymentCommand >--- Deployment
App 1---* Environment 1---* EnvironmentVariable
Environment 1---* Domain
App 1---* WebhookDelivery (audit of GitHub deliveries, by delivery id)
```

- Every user-facing row is owner-scoped. There are no teams.
- `Server` holds the encrypted private key, its fingerprint, and the pinned
  host key (used by the SSH bridge only).
- `App` holds the repository, path, deploy/restart commands, the container
  port and optional resource limits, the current and last-successful commits,
  an optional encrypted webhook secret, and the auto-deploy flag.
- `Environment` is a named target of an app with its own server mapping,
  auto-deploy flag, and health path; `EnvironmentVariable` rows are encrypted
  at rest and only ever read in masked form by the API; `Domain` rows track
  DNS verification status.
- `Deployment` records status (the 12-value spec §13 pipeline), kind
  (`deploy` / `rollback`), both commit SHAs, the commit message when
  webhook-triggered, exit code, timings, the health-check result, and who
  triggered it.
- `DeploymentCommand` is a queued unit of work for one agent, with a
  self-contained payload and a per-claim token.
- `DeploymentLog` is one row per output line, with a monotonic `sequence`.

Three indexes carry real semantics:

- `ix_deployment_logs_deployment_id_sequence` — ordered log reads and the
  `sequence >` cursor used by the stream.
- `uq_deployments_active_per_app` — a *partial* unique index on `app_id` where
  status is any dispatchable active status (everything except `queued`). This
  is the actual concurrency guard; migration `0012` widened it from the
  original `pending`/`running` pair.
- `uq_deployment_commands_active_per_deployment` — a partial unique index on
  `deployment_commands.deployment_id` for queued/claimed commands, so two
  dispatch calls racing (webhook vs promotion) can never hand the agent the
  same deployment twice.

## Deploy request flow

```text
POST /apps/{id}/deploy   (or a verified GitHub webhook, or the CLI)
  |
  1. authenticate, load the app (owner-scoped)
  2. reject if a dispatchable deployment is already active
     (service check -> friendly 409; webhook pushes queue instead)
  3. insert a Deployment in `pending`  (unique index -> 409 on a race)
  4. write an audit row, commit
  5. dispatch: if the server has an agent, enqueue a DeploymentCommand;
     otherwise schedule the SSH bridge runner as a background task
  6. return 202 with the deployment
        |
        +-->  (agent path)  the agent claims the command, runs its staged
        |     pipeline (clone, build, start, health check, proxy, cleanup),
        |     and posts stage/log/health events that advance the pipeline and
        |     stream into the dashboard; the result closes the command
        |
        +-->  (SSH path)  DeploymentRunner
              - mark running, log "Deployment started", notify the event bus
              - decrypt the server's private key
              - read the current commit  (git rev-parse HEAD)
              - run the deploy command   (bash -lc 'set -e; cd <path>; <command>')
              - persist every stdout/stderr line, notify the event bus
              - on exit 0: read the new commit, update the app, mark success
                otherwise: record stderr, mark failed
              - always: set finished_at and duration
        |
        v  (either path, on a terminal status)
   promote the app's oldest `queued` deployment and dispatch it
```

### Why the guard is in two places

The service-layer check produces a helpful message naming the in-flight
deployment. It cannot be authoritative: two workers can both pass it in the same
instant. The partial unique index settles that race, and the resulting
`IntegrityError` is translated into a `409`. Belt and braces, with the database
holding the braces. The same pattern guards the command queue: a partial unique
index ensures at most one live command per deployment.

## Log streaming

Whatever executes a deployment signals an in-process event bus
(`services/deployment_events.py`) each time it persists output — the SSH
bridge runner and the agent event ingestion path alike. The SSE stream waits
on that signal rather than polling every second per connection.

A 15-second timeout on the wait acts as a backstop: a missed signal delays
output rather than losing it, and the same code keeps working if the executor
is later moved to a separate process. That timeout doubles as the heartbeat
interval.

Log `sequence` comes from a per-deployment counter — local to the runner's
`run()` on the SSH path, and read once per event batch on the agent path — not
from `len(logs)`, which was O(n) per line.

## SSH layer

`services/ssh_service.py` is the only place that opens an SSH connection. Note
the scope: this layer serves the SSH bridge (path A) only — agent-driven
deployments never open SSH; the agent authenticates to the control plane with
its own hashed bearer token.

- `scan_host_key()` fetches the key a server presents, without authenticating.
  Used at onboarding so the fingerprint can be shown before it is trusted.
- `run_command()` requires a pinned host key. Passing none raises
  `HostKeyUnpinnedError` rather than connecting unverified — a missing pin is a
  bug or a misconfiguration, never a reason to skip verification.
- A mismatch raises `HostKeyMismatchError` before authentication, so the
  decrypted private key is never transmitted to an unverified host.

Host keys are stored as `"<algorithm> <base64>"`, the same information
`known_hosts` carries, with a `SHA256:` fingerprint derived for display.

## Encryption

Fernet, keyed by SHA-256 of `ENCRYPTION_KEY`, with the ciphertext prefixed by a
key id:

```text
v1:gAAAAAB...
```

The prefix is what makes rotation tractable: the active key writes new values
while retired keys, listed in `ENCRYPTION_KEYS_RETIRED`, still decrypt old ones.
Values written before key ids existed have no prefix and fall back to the active
key. `needs_rewrap()` identifies values still on an old key.

## Frontend

A deliberately small stack: React 19 with Vite, no router library, no state
library, no data-fetching library.

- `routes.ts` — a ~40-line path matcher over `history.pushState`
- `api/client.ts` — one `request()` wrapper; attaches the token, normalises
  FastAPI's error shapes into `Error.message`
- `hooks/useAuth.tsx` — token in `localStorage`, current user, login/logout
- `hooks/useDeploymentStream.ts` — reads the SSE endpoint with `fetch`
  (`EventSource` cannot send an `Authorization` header), parses frames,
  deduplicates by `sequence`
- `lib/bootstrap/` — per-stack setup-plan generators, pure functions with no I/O
- `pages/` — one file per screen

The token lives in `localStorage`, which is XSS-readable. That trade-off is
discussed in [Security model](security.md#tokens-are-stored-in-localstorage).

## Known architectural limits

| Limit | Consequence | Intended direction |
| --- | --- | --- |
| SSH-bridge deployments run in the API process | A restart mid-deploy orphans the row; startup and periodic sweeps reclaim it | The agent path already executes on the VPS; retire the SSH bridge once agent coverage is the norm |
| The event bus is in-process | Multi-worker setups fall back to the 15s poll for streaming | Postgres `LISTEN`/`NOTIFY` or Redis pub/sub |
| In-memory rate limiting by default | Per-process counters unless `REDIS_URL` is set | Already solved; make Redis the default in production |
| Owner-scoped only | No teams, no roles | Multi-user teams with per-app permissions |
| Environment variables are stored, not injected | The agent payload carries the schema for them, but injection into builds/containers is not wired end to end yet | Pass decrypted environment variables through the deploy command payload |
| SSL is verified, not issued | Domains verify by DNS; certificates are still yours to provision | Let's Encrypt automation on top of the domain flow |

## Design decisions worth stating

**Two execution paths, one record.** The agent is the strategic path — it can
build Docker images, health-check, and switch traffic with zero downtime —
while the SSH bridge keeps the product working for servers without an agent.
Both write the same deployment records, stream over the same SSE endpoint, and
audit to the same table. The routing decision lives in one service
(`agent_dispatch.dispatch_deployment`), not at the call sites.

**Commands, not conventions.** DeployDock runs the commands you already run
(SSH path) or builds what you already have (agent path, Docker). This is why it
works with existing apps, and it is why a DeployDock account is as powerful as
shell access.

**The database is the source of truth for concurrency.** Anything a second
worker could get wrong is enforced by a constraint, not by process state — for
deployments and for the agent command queue alike.

**The agent is sandboxed by design.** It executes only its own staged pipeline
from self-contained command payloads; it never receives or runs arbitrary
shell from the control plane, and it never queries the database directly.

**Rollback is a first-class deployment.** A rollback creates its own record
rather than mutating the original, so history shows what actually happened.
