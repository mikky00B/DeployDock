# Architecture

## Components

```text
Browser (React + Vite)
   |  JSON over HTTPS, bearer token
   v
FastAPI backend  ----  PostgreSQL (users, servers, apps, deployments, logs, audit)
   |                \
   |                 --  Redis (optional: login rate limiting)
   |  SSH on demand, host key verified
   v
Target VPS  ->  your existing systemd / Docker / nginx app
```

There is no agent on the target server. DeployDock opens an SSH connection when
it has something to do, runs your command, streams the output, and closes.

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
```

- Every row is owner-scoped. There are no teams.
- `Server` holds the encrypted private key, its fingerprint, and the pinned host
  key.
- `App` holds the repository, path, deploy/restart commands, and the current and
  last-successful commits.
- `Deployment` records status, kind (`deploy` / `rollback`), both commit SHAs,
  exit code, timings, and who triggered it.
- `DeploymentLog` is one row per output line, with a monotonic `sequence`.

Two indexes carry real semantics:

- `ix_deployment_logs_deployment_id_sequence` — ordered log reads and the
  `sequence >` cursor used by the stream.
- `uq_deployments_active_per_app` — a *partial* unique index on `app_id` where
  status is `pending` or `running`. This is the actual concurrency guard.

## Deploy request flow

```text
POST /apps/{id}/deploy
  |
  1. authenticate, load the app (owner-scoped)
  2. reject if a deployment is already active (service check -> friendly 409)
  3. insert a pending Deployment  (unique index -> 409 on a race)
  4. write an audit row, commit
  5. schedule DeploymentRunner.run as a background task
  6. return 202 with the pending deployment
        |
        v  (background)
  DeploymentRunner
   - mark running, log "Deployment started", notify the event bus
   - decrypt the server's private key
   - read the current commit  (git rev-parse HEAD)
   - run the deploy command   (bash -lc 'set -e; cd <path>; <command>')
   - persist every stdout/stderr line, notify the event bus
   - on exit 0: read the new commit, update the app, mark success
     otherwise: record stderr, mark failed
   - always: set finished_at and duration
```

### Why the guard is in two places

The service-layer check produces a helpful message naming the in-flight
deployment. It cannot be authoritative: two workers can both pass it in the same
instant. The partial unique index settles that race, and the resulting
`IntegrityError` is translated into a `409`. Belt and braces, with the database
holding the braces.

## Log streaming

The runner and the SSE endpoint live in the same process, so the runner signals
an in-process event bus (`services/deployment_events.py`) each time it persists
output. The stream waits on that signal rather than polling every second per
connection.

A 15-second timeout on the wait acts as a backstop: a missed signal delays
output rather than losing it, and the same code keeps working if the runner is
later moved to a separate process. That timeout doubles as the heartbeat
interval.

Log `sequence` comes from a counter on the runner, not from `len(logs)`. A
single runner owns a deployment end to end, so the counter is both correct and
O(1) per line.

## SSH layer

`services/ssh_service.py` is the only place that opens an SSH connection.

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
| Deployments run in the API process | A restart mid-deploy orphans the row; a startup sweep reclaims it | Move the runner to a dedicated worker (arq / dramatiq / Celery) |
| The event bus is in-process | Multi-worker setups fall back to the 15s poll for streaming | Postgres `LISTEN`/`NOTIFY` or Redis pub/sub |
| In-memory rate limiting by default | Per-process counters unless `REDIS_URL` is set | Already solved; make Redis the default in production |
| Owner-scoped only | No teams, no roles | Multi-user teams with per-app permissions |
| Commands stored in the database | No review trail for a command change | Optional `deploydock.yml` in the repository |

## Design decisions worth stating

**Agentless.** No daemon to install, version, or upgrade on target servers. The
cost is that DeployDock cannot see anything between deploys.

**Commands, not conventions.** DeployDock runs the commands you already run.
This is why it works with existing apps, and it is why a DeployDock account is
as powerful as shell access.

**The database is the source of truth for concurrency.** Anything a second
worker could get wrong is enforced by a constraint, not by process state.

**Rollback is a first-class deployment.** A rollback creates its own record
rather than mutating the original, so history shows what actually happened.
