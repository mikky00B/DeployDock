# API reference

Base path: `/api/v1`. Interactive docs are served by FastAPI at `/docs`
(OpenAPI JSON at `/openapi.json`) and are always authoritative for exact schemas.

## Authentication

Send the access token as a bearer header:

```http
Authorization: Bearer <access_token>
```

Every resource is scoped to its owner. Requesting someone else's resource
returns `404`, not `403` — the API does not confirm that an id exists for
another user.

### `POST /auth/register`

```json
{ "email": "owner@example.com", "password": "...", "full_name": "Deploy Owner" }
```

`201` with `{ "user": {...}, "token": { "access_token": "...", "token_type": "bearer" } }`.
`409` if the email is taken. Emails are normalised to lowercase.

### `POST /auth/login`

```json
{ "email": "owner@example.com", "password": "..." }
```

`200` with the same shape as register. `401` on bad credentials. `429` when rate
limited, with a `Retry-After` header.

### `POST /auth/logout`

`200`. Client-side only — tokens are stateless and cannot be revoked
server-side.

### `GET /auth/me`

`200` with the current user.

## Servers

### `POST /servers`

```json
{ "name": "Main VPS", "host": "203.0.113.10", "port": 22, "username": "deploy" }
```

Omit `private_key` to have DeployDock generate an ed25519 keypair; the response
carries `public_ssh_key` for you to install on the server. Supplying
`private_key` is the manual option.

Responses never include the private key or its ciphertext.

### `GET /servers`, `GET /servers/{id}`

List or fetch. Response fields include `status`
(`unknown` / `connected` / `unreachable`), `private_key_fingerprint`,
`known_host_key_fingerprint`, `known_host_key_pinned_at`,
`last_connection_check_at`, and `last_connection_error`.

### `PATCH /servers/{id}`

Partial update. Changing `host` or `port` clears the pinned host key and resets
status to `unknown`. Sending a new `private_key` re-encrypts it and resets
status.

### `DELETE /servers/{id}`

`204`. Cascades to that server's apps and their deployments.

### `POST /servers/{id}/test-connection`

Runs `echo deploydock-ok` over SSH. On the first call it pins the server's host
key.

```json
{
  "success": true,
  "status": "connected",
  "message": "SSH connection succeeded",
  "host_key_fingerprint": "SHA256:..."
}
```

Returns `200` even on failure, with `success: false` and the reason in
`message` — the request succeeded, the connection did not.

### `POST /servers/{id}/host-key`

Re-pins the host key to whatever the server presents now. Use only after
verifying the change is legitimate.

```json
{
  "fingerprint": "SHA256:new",
  "algorithm": "ssh-ed25519",
  "previous_fingerprint": "SHA256:old",
  "message": "Host key pinned. Verify this fingerprint against the server itself."
}
```

`502` if the server cannot be reached. Audited as `server.host_key_pinned`.

## Apps

### `POST /apps`

```json
{
  "name": "Watchdog",
  "server_id": "...",
  "repository_url": "https://github.com/example/watchdog.git",
  "branch": "main",
  "app_path": "/opt/watchdog",
  "service_name": "watchdog",
  "deploy_command": "git pull origin main\nsudo systemctl restart watchdog",
  "restart_command": "sudo systemctl restart watchdog",
  "healthcheck_url": "https://watchdog.example.com/health"
}
```

`deploy_command` is executed as shell on the target server. See
[Security model](security.md#deploy-commands-are-arbitrary-shell).

`healthcheck_url` is recorded and surfaced in the dashboard. Agent-driven
deployments probe it (or the configured health path) after starting the new
container and only mark the deployment successful when it passes; the SSH
bridge records it for reference.

Optional agent-deployment fields: `port` (the TCP port the app listens on
inside its container — required for agent-driven deploys), `cpu_limit`
(Docker `--cpus`, e.g. `1.5`), and `memory_limit` (Docker `--memory`, e.g.
`512m`).

### `GET /apps`, `GET /apps/{id}`, `PATCH /apps/{id}`, `DELETE /apps/{id}`

Standard CRUD. Delete cascades to the app's deployments.

### `GET /apps/{id}/status`

`systemctl is-active` for the app's service. Returns `"unknown"` when no
`service_name` is set.

### `POST /apps/{id}/restart`

Runs the restart command. `400` when the app has neither `restart_command` nor
`service_name`. Audited as `service.restarted`.

### `GET /apps/{id}/logs`

Last 100 `journalctl` lines for the service. `400` without a `service_name`,
`502` if the command fails.

## Deployments

### `POST /apps/{id}/deploy`

`202` with the created deployment in `pending`. Execution is asynchronous.

`409` when a dispatchable deployment for that app is already in flight — any
active status except `queued` (pending, running, cloning, building, testing,
deploying, health_check). GitHub webhook pushes queue instead of conflicting;
see [Deployments](deployments.md).

If the app's server has a registered agent, the deployment is handed to it as a
command; otherwise it falls back to the SSH bridge runner.

### `GET /apps/{id}/deployments`

Newest first.

### `GET /deployments/{id}`

Deployment detail including logs. Fields: `status`, `kind`, `commit_sha`,
`previous_commit_sha`, `commit_message`, `exit_code`, `error_message`,
`started_at`, `finished_at`, `duration_seconds`, `triggered_by`, and the
health-check result columns (`healthcheck_url`, `healthcheck_status_code`,
`healthcheck_ok`, `healthcheck_error`) reported by the agent engine.

Statuses (spec §13 pipeline): `pending`, `queued`, `cloning`, `building`,
`testing`, `deploying`, `health_check`, `running`, `success`, `failed`,
`canceled`, `rolled_back`. The active group is everything before `success`;
agent-driven deployments advance through the pipeline stages as the agent
reports them.

### `POST /deployments/{id}/cancel`

Cancels a non-terminal deployment. `200` with the canceled deployment;
idempotent if it is already `canceled`; `409` when the deployment is in another
terminal state. Audited as `deployment.canceled`, and any deployment queued
behind the canceled one is promoted.

### `GET /deployments/{id}/logs`

Log lines ordered by `sequence`, each with `stream`
(`stdout` / `stderr` / `system`).

### `GET /deployments/{id}/stream`

Server-Sent Events. Content type `text/event-stream`.

```text
event: log
data: {"stream":"stdout","line":"pulling","sequence":3}

event: heartbeat
data: {"status":"running"}

event: status
data: {"status":"success"}
```

Terminates after a terminal `status` event. Heartbeats every 15 idle seconds.
Because SSE cannot send custom headers from `EventSource`, the dashboard reads
this endpoint with `fetch` and a bearer header.

### `POST /deployments/{id}/rollback`

`202` with a new deployment of `kind: "rollback"`, targeting the app's most
recent successful commit before this one.

- `400` when no previous successful commit exists.
- `400` when the app has no restart command or service name.
- `409` when another deployment for that app is in flight.

## Agents

Agents are the Go daemons that execute deployments on a server. Full details,
including the token model, are in [Agent protocol](agent-protocol.md).

### `POST /agents/registration-tokens`

Mints a single-use registration token (shown once, stored hashed). Body:
`{"server_id": "<uuid or null>", "ttl_seconds": 900}`. `201` with
`{"token": "dck_rt_...", "expires_at": "..."}`.

### `POST /agents/register`

Called once by the agent with the registration token as the bearer credential.
Body: `{"name", "agent_version", "os", "arch"}`. `201` with
`{"agent_id", "agent_token": "dck_at_...", "heartbeat_interval_seconds"}`.
`401` when the token is unknown, expired, or already used.

### `GET /agents`

Lists the caller's agents with derived `status` (`online` when a heartbeat
arrived within `AGENT_OFFLINE_AFTER_SECONDS`, else `offline`), reported
metrics, and version information.

### `POST /agents/{id}/heartbeat`

Agent-authenticated liveness report with optional CPU/memory/disk metrics.
Returns the heartbeat interval the server wants.

### `POST /agents/{id}/rotate-token`

User-authenticated. Revokes the current agent token and returns a new one
(shown once). Audited as `agent.token_rotated`.

### `GET /agents/{id}/commands`

Agent-authenticated. Atomically claims the agent's oldest queued command and
returns it with a self-contained payload and a one-time claim token. Empty
list when idle.

### `POST /agents/{id}/commands/{command_id}/result`

Agent-authenticated close-out of a claimed command; the claim token must
match. `409` on a wrong or stale token.

### `POST /agents/{id}/events`

Agent-authenticated batch of deployment events (`deployment_started`,
`stage_started`, `stage_completed`, `log`, `health_check_passed`,
`health_check_failed`, `deployment_completed`, `deployment_failed`). Returns
`{"accepted": N, "rejected": M}`; rejected events are logged server-side.
Events never overwrite a terminal deployment status.

## Environments

Each app can have named environments (production, staging, …), each with its
own server, auto-deploy flag, variables, and domains.

### `POST /apps/{id}/environments`

`{"name": "production", "server_id": "...", "auto_deploy": true,
"health_path": "/health"}` → `201`. The server must be the app's own server
for now. `409` on a duplicate name.

### `GET /apps/{id}/environments`, `GET /environments/{id}`,
`DELETE /environments/{id}`

Standard CRUD.

### `PUT /environments/{id}/variables/{key}`

`{"key": "DATABASE_URL", "value": "..."}`. The value is encrypted at rest with
the control-plane key. `204`/`200` responses never contain the value.

### `GET /environments/{id}/variables`

Masked reads: a list of `{ "key": "...", "set": true }` — presence only, never
values.

### `DELETE /environments/{id}/variables/{key}`

Removes the variable. `404` when unset.

### `POST /environments/{id}/domains`

`{"hostname": "app.example.com"}` → `201` with the domain in `pending`.

### `POST /domains/{id}/verify`

Verifies by DNS: the hostname must resolve to the server's IP. Returns
`{"verified": bool, "message", "expected_ip", "resolved_ips"}` and updates the
domain's `status`. Audited.

## Webhooks

### `POST /apps/{id}/webhook-secret`

Mints the app's GitHub webhook signing secret. Shown once; stored encrypted.
`201` with `{"webhook_secret": "whsec_...", "header": "X-Hub-Signature-256"}`.

### `POST /webhooks/github`

Public GitHub webhook receiver. Verifies the `X-Hub-Signature-256` HMAC against
the matching app's secret, deduplicates on `X-GitHub-Delivery` (replay
protection), validates the repository, branch, and the app's auto-deploy flag,
then creates a deployment carrying the push's commit SHA and message. Pushes
arriving while another deployment is active are queued (spec §42) rather than
rejected. Always answers `202` with a `webhook_result` of `deployed`, `queued`,
`ignored`, or `rejected`.

## Dashboard

### `GET /dashboard`

Aggregated counts and recent activity for the current user.

## Metrics

- `GET /metrics` — Prometheus text format: deployment totals per status,
  deployment duration sum/count, server and app gauges, and agent
  online/total counts. Unauthenticated; front with proxy auth if you do not
  want it exposed.

## Health

Unauthenticated, outside `/api/v1`:

- `GET /health` — `{"status":"ok","service":"deploydock-api"}`
- `GET /health/ready` — `{"status":"ok","database":"reachable"}`, or `503` with
  a remediation hint

## Error shape

FastAPI's standard envelope:

```json
{ "detail": "Deployment not found" }
```

Validation errors return `422` with `detail` as an array of
`{ "loc": [...], "msg": "...", "type": "..." }`.

| Status | Meaning here |
| --- | --- |
| `400` | The request is valid but the operation is not possible (no rollback target, no restart command) |
| `401` | Missing, malformed, or expired token (user JWT, agent token, or registration token) |
| `404` | Not found, or owned by another user |
| `409` | A deployment is already in flight, a host key is unpinned/mismatched, or a stale command claim was submitted |
| `422` | Request body failed validation |
| `429` | Login or registration rate limit tripped; see `Retry-After` |
| `502` | An SSH command or host key scan failed |
| `503` | The database is unreachable |
