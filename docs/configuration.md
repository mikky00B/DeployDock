# Configuration

The backend loads settings from `backend/.env` via `backend/app/core/config.py`
(Pydantic settings). Environment variables always win over the file. Example
values live in `backend/.env.example`.

The frontend reads `VITE_API_BASE_URL` from `frontend/.env` at build time.

## Backend variables

### Core

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | `production` / `prod` enables the guardrails below |
| `API_HOST` | `127.0.0.1` | Bind address when run directly |
| `API_PORT` | `8000` | Bind port when run directly |
| `DATABASE_URL` | local PostgreSQL | Async SQLAlchemy URL; must use `postgresql+asyncpg://` |
| `CORS_ORIGINS` | localhost:5173 | Comma-separated allowed origins for the dashboard |

### Authentication

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | `change-me` | Signs access tokens (HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Token lifetime |

Generate a real key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

There is no server-side token revocation list. Changing `SECRET_KEY`
invalidates every issued token at once, which is the blunt way to log everyone
out. Keep the lifetime short.

### Encryption at rest

| Variable | Default | Purpose |
| --- | --- | --- |
| `ENCRYPTION_KEY` | `change-me-32-byte-key` | Encrypts stored SSH private keys |
| `ENCRYPTION_KEY_ID` | `v1` | Tags values written with the active key |
| `ENCRYPTION_KEYS_RETIRED` | empty | `key_id:secret` pairs accepted for decryption only |

Stored ciphertext looks like `v1:gAAAAAB...`. The prefix records which key wrote
it, which is what makes rotation possible without a big-bang re-encrypt. See
[Operations → rotating the encryption key](operations.md#rotating-the-encryption-key).

Values written before key ids existed have no prefix and are decrypted with the
active key.

### Rate limiting

| Variable | Default | Purpose |
| --- | --- | --- |
| `REDIS_URL` | unset | Shared rate-limit counters across workers |
| `LOGIN_MAX_ATTEMPTS` | `5` | Failed attempts per window, per account |
| `LOGIN_WINDOW_SECONDS` | `60` | Sliding window length |
| `REGISTER_MAX_ATTEMPTS` | `10` | Registration attempts per source address (every attempt counts) |
| `REGISTER_WINDOW_SECONDS` | `3600` | Registration throttle window |
| `TRUST_PROXY_HEADERS` | `false` | Honor `X-Forwarded-For` for client IP resolution |

Attempts are counted in three buckets for login: per source IP, per account,
and per IP+account pair. The per-IP bucket is deliberately looser (5x) because
one IP can legitimately front many users behind NAT or a reverse proxy.
Registration is public, so every attempt counts against the source address.

`TRUST_PROXY_HEADERS` only enable behind a reverse proxy you control: it makes
`client_ip()` read the first `X-Forwarded-For` hop instead of the socket
address. With it off (the default), a spoofed header is ignored; with it on
behind nginx, the proxy must actually set the header.

Without `REDIS_URL` the limiter is per-process and the app logs a warning at
startup. With more than one uvicorn worker that means the effective limit is
multiplied by the worker count. Install the extra with
`pip install -e ".[redis]"`.

### Deployment execution

| Variable | Default | Purpose |
| --- | --- | --- |
| `DEPLOY_TIMEOUT_SECONDS` | `900` | Hard limit on a deploy command |
| `ROLLBACK_TIMEOUT_SECONDS` | `300` | Hard limit on a rollback command |
| `ORPHAN_DEPLOYMENT_TIMEOUT_SECONDS` | `3600` | Age at which a stuck deployment is reclaimed at startup |

Raise `DEPLOY_TIMEOUT_SECONDS` if you have genuinely slow builds. The orphan
timeout should stay comfortably above your longest deploy, otherwise a startup
during a long deploy could mark a live one as failed.

### Agents

| Variable | Default | Purpose |
| --- | --- | --- |
| `HEARTBEAT_INTERVAL_SECONDS` | `30` | Cadence the server asks agents to report at |
| `AGENT_REGISTRATION_TOKEN_TTL_SECONDS` | `900` | Lifetime of a single-use registration token |
| `AGENT_OFFLINE_AFTER_SECONDS` | `90` | Heartbeat age after which an agent shows as offline |
| `AGENT_COMMAND_LEASE_SECONDS` | `1800` | Age after which a claimed command is assumed lost; the sweep fails it and its deployment |
| `AGENT_RECLAIM_SWEEP_SECONDS` | `300` | How often the expired-lease sweep runs |

`AGENT_COMMAND_LEASE_SECONDS` must exceed your longest legitimate deploy
(`DEPLOY_TIMEOUT_SECONDS`), or a healthy slow deploy would be reclaimed while
still running.

## Frontend variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | *(unset — same origin)* | API origin when it differs from the dashboard's |

Unset, the dashboard calls `/api/...` on its own origin: Vite's dev server
proxies those to `http://127.0.0.1:8000` (see `frontend/vite.config.ts`), and in
production nginx can do the same. Set an absolute URL only when the API lives on
a different origin. Vite inlines this at build time. For containers it is a
build argument (`docker compose build --build-arg VITE_API_BASE_URL=...`), not a
runtime setting.

## Production guardrails

With `APP_ENV=production`, the app refuses to start when:

- `SECRET_KEY` is `change-me` or shorter than 32 characters.
- `ENCRYPTION_KEY` is a known default or shorter than 32 characters.
- `CORS_ORIGINS` contains `*`.
- `CORS_ORIGINS` points at `localhost`, `127.0.0.1`, or `0.0.0.0`.

A malformed `ENCRYPTION_KEYS_RETIRED` also fails at startup rather than at the
first decrypt, so a typo surfaces immediately instead of when someone tries to
deploy.

These checks are a floor, not a security review. They cannot tell whether your
secrets are actually secret.

## Secrets and app environment files

The recommendation for app runtime secrets:

- Keep your app's production `.env` on the target server, or use the app's
  environment variables in DeployDock for secrets the deployment pipeline
  itself needs.
- Do not store app secrets in deploy commands — they end up in logs.

DeployDock encrypts what it stores at rest: SSH private keys and environment
variables (Fernet, keyed by `ENCRYPTION_KEY`, with key ids for rotation).
Environment variables are only ever readable in masked form through the API,
and their values are excluded from audit logs. The decrypted values are
reserved for deployment injection and never pass back through the API.
