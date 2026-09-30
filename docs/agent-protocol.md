# DeployDock Agent Protocol — v1

This is the Phase 1 deliverable (spec §68): the stable contract between the FastAPI
control plane and the Go agent. It is intentionally minimal — registration, auth,
heartbeat, system info — and will be extended with commands/events in Phase 3
without breaking these foundations.

Design rules from the master spec (§10, §24, §25):

- The agent always makes **outbound** HTTPS calls to the control plane. No inbound
  port is ever opened on the VPS.
- The agent **never** touches PostgreSQL. Every read/write goes through this API.
- The agent authenticates with its own token, distinct from any user's JWT.
- The control plane owns all state; the agent only reports what it observes.

## Transport and auth

All endpoints live under `/api/v1`. Requests and responses are JSON.

| Caller | Credential | How it is used |
|---|---|---|
| Control-plane user | JWT (existing `Authorization: Bearer` scheme) | Minting registration tokens, listing/rotating agents |
| Registering agent | Registration token | One call only: `POST /agents/register` |
| Registered agent | Agent token | Every subsequent call: `Authorization: Bearer <agent token>` |

Token properties:

- **Registration tokens** are single-use, expire after 15 minutes, and are stored
  server-side as SHA-256 hashes. The plaintext value is shown exactly once.
- **Agent tokens** are 32 random bytes, base64url-encoded, shown exactly once at
  registration, and stored server-side as SHA-256 hashes. Rotation revokes the old
  token immediately.
- Both token types are opaque; the agent must persist its agent token on disk with
  owner-only permissions (`0600`).

## Endpoints

### `POST /api/v1/agents/registration-tokens` (user auth)

Mint a registration token, optionally bound to one server row.

```json
// request
{ "server_id": "uuid-or-null", "ttl_seconds": 900 }
// response 201
{
  "token": "dck_rt_...",           // plaintext, shown once
  "expires_at": "2026-09-03T12:15:00Z"
}
```

### `POST /api/v1/agents/register` (registration token)

Sent once by the agent during onboarding. Creates the agent row and returns its
long-lived agent token.

```json
// request
{
  "name": "nyc-1.vps",             // defaults to hostname
  "agent_version": "0.1.0",
  "os": "linux",
  "arch": "amd64"
}
// headers
Authorization: Bearer dck_rt_...
// response 201
{
  "agent_id": "uuid",
  "agent_token": "dck_at_...",     // plaintext, shown once — persist this
  "heartbeat_interval_seconds": 30
}
```

Errors: `401` unknown/expired/used registration token.

### `POST /api/v1/agents/{agent_id}/heartbeat` (agent token)

Sent on an interval (server-provided at registration, default 30s). Updates
liveness and reports system metrics. A heartbeat that only proves liveness may
send an empty `metrics` object.

```json
// request
{
  "agent_version": "0.1.0",
  "metrics": {
    "cpu_percent": 21.5,
    "memory_percent": 43.0,
    "disk_percent": 38.2
  }
}
// response 200
{
  "status": "ok",
  "heartbeat_interval_seconds": 30,
  "server_time": "2026-09-03T12:00:31Z"
}
```

Errors: `401` invalid agent token · `403` token belongs to a different agent ·
`409` agent has been revoked.

### `GET /api/v1/agents` (user auth)

List the caller's agents. `status` is derived: `online` if the last heartbeat is
within `agent_offline_after_seconds` (default 90 = 3 missed intervals), else
`offline`.

```json
// response 200
[
  {
    "id": "uuid",
    "name": "nyc-1.vps",
    "server_id": null,
    "status": "online",
    "agent_version": "0.1.0",
    "os": "linux",
    "arch": "amd64",
    "last_heartbeat_at": "2026-09-03T12:00:31Z",
    "metrics": { "cpu_percent": 21.5, "memory_percent": 43.0, "disk_percent": 38.2 },
    "created_at": "..."
  }
]
```

### `POST /api/v1/agents/{agent_id}/rotate-token` (user auth)

Revoke the current agent token and issue a new one (shown once). For suspected
compromise or credential hygiene.

```json
// response 200
{ "agent_id": "uuid", "agent_token": "dck_at_...", "heartbeat_interval_seconds": 30 }
```

## Derived status & audit

- A heartbeat stamps `last_heartbeat_at`; `status` is never stored, only derived,
  so clock drift between agent and server cannot flip stored state.
- The control plane writes audit log entries for `agent.registered` and
  `agent.token_rotated`. Heartbeats are not audited (they would flood the log).

## Phase 3 extension points (implemented)

- `GET /api/v1/agents/{agent_id}/commands` — claims the agent's oldest queued
  command (one at a time; empty list when idle). The payload is self-contained:
  deployment id, kind (`deploy`/`rollback`), target commit, and the app spec
  (repository, branch, path, container port, health path, container base,
  resource limits).
- `POST /api/v1/agents/{agent_id}/commands/{command_id}/result` — closes the
  command out; the claim token minted at claim time must be echoed back.
- `POST /api/v1/agents/{agent_id}/events` — batches of
  `deployment_started`, `stage_started`, `stage_completed`, `log`,
  `health_check_passed`/`health_check_failed`, `deployment_completed`,
  `deployment_failed`. The control plane writes these into `deployment_logs`,
  advances the 12-value deployment status, and wakes the SSE stream; terminal
  statuses are never overwritten (a cancel always wins over a racing result).
- Idempotency: one in-flight command per agent; a stale claim token is
  rejected with 409.
