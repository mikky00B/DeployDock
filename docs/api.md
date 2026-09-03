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

`healthcheck_url` is stored and surfaced in the dashboard but is not probed
automatically in v1.

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

`409` when a deployment for that app is already `pending` or `running`.

### `GET /apps/{id}/deployments`

Newest first.

### `GET /deployments/{id}`

Deployment detail including logs. Fields: `status`, `kind`, `commit_sha`,
`previous_commit_sha`, `exit_code`, `error_message`, `started_at`,
`finished_at`, `duration_seconds`, `triggered_by`.

Statuses: `pending`, `running`, `success`, `failed`, `canceled`. There is no
cancel endpoint in v1 — `canceled` exists for interrupted runs recorded by hand.

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

## Dashboard

### `GET /dashboard`

Aggregated counts and recent activity for the current user.

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
| `401` | Missing, malformed, or expired token |
| `404` | Not found, or owned by another user |
| `409` | A deployment is already in flight, or a host key is unpinned/mismatched |
| `422` | Request body failed validation |
| `429` | Login rate limit tripped; see `Retry-After` |
| `502` | An SSH command or host key scan failed |
| `503` | The database is unreachable |
