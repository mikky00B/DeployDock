# Operations

## Production checklist

- [ ] `APP_ENV=production`
- [ ] `SECRET_KEY` and `ENCRYPTION_KEY` are long random values, not defaults
- [ ] `CORS_ORIGINS` is your real dashboard origin, over HTTPS
- [ ] PostgreSQL is not reachable from the internet
- [ ] `REDIS_URL` is set if you run more than one API worker
- [ ] TLS terminates at a reverse proxy in front of the API and dashboard
- [ ] Database backups are running, and `ENCRYPTION_KEY` is backed up separately
- [ ] Every server's host key fingerprint has been verified out of band
- [ ] Deploy users are non-root with narrow sudoers entries

## Running the API

```bash
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

### Why one worker by default

Two things are per-process today:

1. **Deployments run in the API process** as FastAPI background tasks. With
   several workers a deploy runs in whichever worker accepted the request, and
   the SSE log stream may be served by a different one. Streaming still works
   (the stream falls back to reading the database), but output arrives on the
   idle-poll interval rather than instantly.
2. **The login rate limiter is in-memory** unless `REDIS_URL` is set, so N
   workers means N separate counters.

Set `REDIS_URL` before scaling workers up. The database-level guard on
concurrent deployments is safe across workers either way — that one is enforced
by a unique index, not by process state.

### Reverse proxy notes

For the log stream, disable response buffering on `/api/v1/deployments/*/stream`.
The API already sets `X-Accel-Buffering: no`, which nginx honours; other proxies
may need explicit configuration. Also raise the read timeout above your
`DEPLOY_TIMEOUT_SECONDS`, or long deploys will have their stream cut.

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_buffering off;
    proxy_read_timeout 1200s;
}
```

`TRUST_PROXY_HEADERS=true` matters behind a proxy: with it set, the API reads
the client address from `X-Forwarded-For` (which nginx sets via the
`proxy_set_header` lines above), so rate-limiting buckets are per real client.
Without it — the default, deliberately — every request appears to come from
the proxy, and the per-IP buckets collapse into one. Do not enable it when the
API is exposed directly, because the header can then be spoofed.

## Migrations

```bash
cd backend
alembic upgrade head          # apply
alembic downgrade -1          # step back one
alembic history               # list
alembic current               # what is applied
```

Two migrations create data-protecting constraints and both first make existing
data satisfy them: `0005` creates the original partial unique index enforcing
one active deployment per app, and `0012` widens that index to every
dispatchable pipeline status and adds the one-live-command-per-deployment
guard — in both cases marking leftover duplicates as failed first, since the
index cannot be created while they exist. If you have in-flight deploys, stop
the API before migrating.

CI runs `upgrade head`, `downgrade base`, `upgrade head`, plus the
concurrency-guard tests against real PostgreSQL on every pull request, so a
migration that cannot be rolled back or enforced fails there.

## Rotating the encryption key

Ciphertext is tagged with the key id that wrote it, so rotation is incremental
rather than all-or-nothing.

1. Generate a new key:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
2. Move the current key into the retired list and install the new one:
   ```text
   ENCRYPTION_KEY=<new key>
   ENCRYPTION_KEY_ID=v2
   ENCRYPTION_KEYS_RETIRED=v1:<old key>
   ```
3. Restart the API. Values written under `v1` still decrypt; new writes use `v2`.
4. Re-wrap existing values by editing each server and re-submitting its private
   key, or by generating a fresh keypair for it. `secret_needs_rewrap()` in
   `app/core/secrets.py` identifies values still on an old key.
5. Once nothing is left on `v1`, drop it from `ENCRYPTION_KEYS_RETIRED`.

Do not remove a key id from the retired list while values still reference it —
those values become permanently unreadable. There is no recovery.

## Rotating the signing key

Changing `SECRET_KEY` invalidates every issued token immediately. That is the
intended way to force everyone to log in again. There is no gradual rollover.

## Backups

Back up two things, and test restoring both:

1. The PostgreSQL database.
2. `ENCRYPTION_KEY` (and any retired keys), stored separately from the database
   backup.

A database backup without the key cannot decrypt stored SSH private keys. Both
together are enough to reach every one of your servers, so protect the pair
accordingly.

```bash
pg_dump --format=custom --file=deploydock-$(date +%F).dump "$DATABASE_URL_LIBPQ"
```

## Monitoring

| Check | Signal |
| --- | --- |
| `GET /health` | Process is up |
| `GET /health/ready` | Database is reachable (503 when not) |
| `GET /metrics` | Prometheus metrics: deployments per status, durations, servers/apps gauges, agents online |
| Startup log `Marked N interrupted deployment(s) as failed` | The API restarted mid-deploy; check the server's real state |
| Startup or periodic log `Reclaimed N expired agent command(s)` | An agent died mid-deploy; its deployment was failed automatically |
| Startup log `No REDIS_URL configured` | Rate limiting is per-process |
| Startup log `Running with default development keys` | Public default secrets are in use; set real ones before exposing |
| Audit rows `server.host_key_pinned` | A host key was re-pinned — confirm it was expected |
| Deployments stuck in a pipeline status past your longest deploy | The agent or runner died; the sweeps reclaim them (startup for SSH-bridge orphans, periodic for expired agent leases) |

Logging is configured in `app/core/logging.py` and keyed off `APP_ENV`.

## Common failures

| Symptom | Cause and fix |
| --- | --- |
| API returns 503 with a database message | PostgreSQL unreachable or migrations not applied |
| Startup fails with `SECRET_KEY must be changed` | `APP_ENV=production` with a default secret; set a real one |
| Startup fails with `ENCRYPTION_KEYS_RETIRED entries must look like` | Malformed retired-key list; use `key_id:secret,key_id:secret` |
| `No encryption key available for key id 'vN'` | A retired key was removed too early; restore it to the list |
| Deploy returns 409 | Another deployment for that app is in flight |
| Deploy returns 409 with a host key message | Host key mismatch or not pinned; see [Server onboarding](server-onboarding.md) |
| Logs arrive in bursts, not live | Proxy buffering is on for the stream path |
| Rate limiting seems not to work | Multiple workers without `REDIS_URL`, or the proxy is not forwarding `X-Forwarded-For` while `TRUST_PROXY_HEADERS` is off |
