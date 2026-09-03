# Deployments

## Deploy commands

Deploy commands are configured per app in the dashboard. DeployDock wraps what
you save:

```bash
bash -lc 'set -e
cd <app_path>
<your deploy command>'
```

`set -e` means a failing step aborts the deploy instead of continuing into a
restart of a half-updated checkout. `<app_path>` is shell-quoted. Your command
text is passed through as written.

Example:

```bash
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
sudo systemctl restart watchdog
```

A deploy records:

- the commit SHA before it started (`previous_commit_sha`)
- the commit SHA after a successful run (`commit_sha`)
- the exit code, duration, and who triggered it
- every stdout and stderr line, in order

## One deployment at a time, per app

Two concurrent deploys of the same app would fight over the same checkout, so
DeployDock allows at most one non-terminal (`pending` or `running`) deployment
per app. A second attempt returns:

```json
HTTP 409
{"detail": "Deployment <id> is already running for this app. Wait for it to finish before starting another."}
```

This is enforced twice on purpose: a service-layer check produces the friendly
message above, and a partial unique index in the database settles races between
two API workers that check at the same instant. Rollbacks are subject to the
same guard.

Different apps deploy in parallel freely, including apps on the same server.

## Interrupted deployments

Deployments currently run inside the API process (FastAPI background tasks). If
that process restarts mid-deploy, the row would otherwise stay `running`
forever — and, because of the guard above, block every future deploy of that
app.

At startup DeployDock sweeps deployments that are still `pending` or `running`
and older than `ORPHAN_DEPLOYMENT_TIMEOUT_SECONDS` (default 1 hour), marks them
`failed`, and records why. The API logs a warning naming how many it reclaimed.

Note what this does **not** do: it cannot stop the shell command that was
already running on the target server. If a deploy was interrupted halfway, check
the server's actual state before re-deploying.

Moving the runner into a dedicated worker process is on the roadmap; it is the
proper fix for this whole class of problem.

## Log streaming

Logs stream to the dashboard over Server-Sent Events at
`GET /api/v1/deployments/{id}/stream`. Three event types:

```text
event: log
data: {"stream":"stdout","line":"pulling","sequence":3}

event: heartbeat
data: {"status":"running"}

event: status
data: {"status":"success"}
```

The stream ends after a terminal `status` event (`success`, `failed`, or
`canceled`). A `heartbeat` every 15 idle seconds keeps reverse proxies from
closing the connection.

The runner signals the stream directly when it writes a line, so output appears
without waiting for a poll. A 15-second timeout acts as a backstop, so a missed
signal delays output rather than losing it. Responses set
`X-Accel-Buffering: no`; if you front the API with nginx, make sure buffering
stays off for this path or logs will arrive in bursts.

Log lines carry a monotonic `sequence`. The dashboard deduplicates by sequence,
so a reconnect that replays lines does not double them up.

## Rollback

A rollback targets the most recent *successful* commit for the app, excluding
the deployment you rolled back from. It runs:

```bash
bash -lc 'set -e
cd <app_path>
git fetch
git checkout <target_commit>
<restart command>'
```

The restart command is the app's `restart_command`, or
`sudo systemctl restart <service_name>` if only a service name is set. An app
with neither cannot be rolled back, and the API says so (`400`).

Rollback is recorded as its own deployment with `kind: "rollback"`, so history
shows what happened rather than silently mutating the original record.

Limits worth knowing:

- Rollback is a `git checkout`, so it reverts code, not database migrations. A
  deploy that ran a destructive migration is not undone by a rollback.
- It leaves the checkout in a detached HEAD state. The next normal deploy's
  `git pull` should be a `git checkout <branch> && git pull` if your deploy
  command assumes it is on a branch.

## Service control

Per app, when a `service_name` is set:

- **Status** — `systemctl is-active <service>`
- **Restart** — the app's restart command, or `sudo systemctl restart <service>`
- **Logs** — `journalctl -u <service> -n 100 --no-pager`

These need matching sudoers entries on the target server. See
[Server onboarding](server-onboarding.md).

## Bootstrap planner

For a new app, the Apps page can generate a setup plan for Django, FastAPI, Go,
or a static React/Vite site. The plan includes server commands, environment
examples, a systemd unit, an nginx snippet, sudoers guidance, and a DeployDock
app payload.

Plans are copied into your own workflow. DeployDock does not execute them — it
still runs only the deploy and service commands you save for the app.

## Audit log

These actions are recorded with the acting user, entity, and metadata:

```text
server.created            server.connection_tested   server.host_key_pinned
app.created               app.updated
deployment.started        deployment.succeeded       deployment.failed
rollback.started
service.restarted
```
