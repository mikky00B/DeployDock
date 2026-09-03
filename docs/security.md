# Security model

DeployDock holds SSH access to your servers. This page states plainly what it
protects, what it does not, and where the sharp edges are.

## Threat model in one line

DeployDock is a single-tenant tool for an operator who already has SSH access to
their own servers. It is not a multi-tenant platform, and it does not attempt to
protect your servers from the person logged into DeployDock.

## What is protected

### SSH host key verification

Every SSH connection verifies the server's host key against a key pinned for
that server. The key is pinned on the first successful connection test and its
fingerprint is shown so you can verify it out of band.

If a server presents a different key, the connection is aborted before
authentication — the decrypted private key is never sent. Re-pinning is an
explicit, audited action, never automatic, because an unexpected host key change
and an interception attempt look identical from here.

Changing a server's host or port clears the pin automatically.

### SSH private keys at rest

Keys are encrypted with Fernet (AES-128-CBC + HMAC-SHA256), derived from
`ENCRYPTION_KEY`. Ciphertext carries a key-id prefix (`v1:...`) so the key can be
rotated while old values stay readable. Keys are decrypted only for the duration
of a single SSH operation and are never returned by the API.

Each server gets its own generated ed25519 keypair by default. Revoking one
server's key affects only that server.

### Passwords

Argon2id, via `argon2-cffi`, with the library's current defaults. Hashes written
by the older pbkdf2-sha256 implementation still verify and are transparently
upgraded to Argon2id on the next successful login.

### Access tokens

JWTs signed HS256 by PyJWT. Decoding pins the accepted algorithm, so a token
cannot claim `none` or a weaker algorithm. Every token carries `iat`, `nbf`,
`exp`, and a unique `jti`, and `sub` plus `exp` are required to be present.

### Login rate limiting

Three buckets — per source IP, per account, and per IP+account pair — so neither
one account nor one source can be hammered by spreading attempts across the
other dimension. Optionally backed by Redis so the limit holds across workers.

### Production configuration guardrails

With `APP_ENV=production`, the app refuses to start on default or weak
`SECRET_KEY` / `ENCRYPTION_KEY` values, on wildcard CORS, or on CORS pointing at
localhost. See [Configuration](configuration.md#production-guardrails).

## What is not protected — read this part

### Deploy commands are arbitrary shell

`deploy_command` and `restart_command` are executed on the target server as the
deploy user. Anyone who can edit an app in DeployDock can run anything that user
can run. This is the product working as designed — it is how DeployDock adapts to
your existing workflow — but the consequence is:

**A DeployDock account is equivalent to shell access on every server that
account's apps point at.** Treat account access accordingly. Narrow sudoers
entries bound what that shell can escalate to; they do not bound the shell.

### No token revocation

There is no server-side revocation list. A leaked token is valid until it
expires. The mitigations are a short `ACCESS_TOKEN_EXPIRE_MINUTES` and, in an
emergency, rotating `SECRET_KEY` — which logs everyone out at once.

### Tokens are stored in localStorage

The dashboard keeps its access token in `localStorage`, so any successful XSS in
the dashboard can read it. This is a deliberate trade-off for a self-hosted,
single-operator panel; a `HttpOnly` cookie plus CSRF protection would be the
stricter design. If you expose the dashboard to a wider audience, that change is
worth making first.

### No multi-user authorisation model

Every resource is scoped to its owner. There are no teams, no roles, and no
shared apps. A second user is a second, fully separate island. Do not treat
per-owner scoping as a permissions system for a team.

### The registration endpoint is open

`POST /api/v1/auth/register` is public. Anyone who can reach the API can create
an account. They will see none of your servers — resources are owner-scoped —
but they can create their own. Put the API behind an allowlist, a VPN, or
reverse-proxy auth once you have registered.

### Rollback does not undo migrations

Rollback is `git checkout` plus a restart. Database migrations that already ran
stay applied.

### Not a secrets manager

DeployDock stores no app secrets by design. Keep your app's `.env` on the target
server.

## Deployment recommendations

1. Put DeployDock behind a VPN or a reverse proxy with its own authentication.
   It does not need to be reachable from the public internet.
2. Terminate TLS at the proxy. Tokens travel in `Authorization` headers.
3. Use a dedicated non-root deploy user per server, with narrow sudoers.
4. Keep `ACCESS_TOKEN_EXPIRE_MINUTES` short.
5. Back up the database *and* `ENCRYPTION_KEY`. The backup is useless without
   the key, and the key is useless without the backup.
6. Verify every host key fingerprint the first time you see it.

## Reporting a vulnerability

Open a private security advisory on the GitHub repository rather than a public
issue.
