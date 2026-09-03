# Contributing

## Setup

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,redis]"

# Frontend
cd frontend
npm install
```

## Running the checks

```bash
# Backend
cd backend
ruff check .          # lint
mypy                  # types (advisory)
pytest -q             # tests

# Frontend
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

CI runs all of these on every push and pull request, plus an Alembic
up/down/up cycle against a real PostgreSQL service. Backend tests run on Python
3.11 and 3.12.

## Tests

Backend tests use pytest with `asyncio_mode = "auto"`, so `async def test_*`
needs no decorator. They run against in-memory SQLite via `aiosqlite`; each
fixture creates a fresh schema from `Base.metadata`.

Conventions worth following:

- **Never open a real SSH connection.** Override the `get_ssh_service`
  dependency with a fake. Fakes need both `run_command()` and, if the code path
  pins host keys, `scan_host_key()`.
- **`TestClient` runs FastAPI background tasks to completion before returning.**
  A deploy triggered through the client is already finished when the call
  returns, so you cannot observe an in-flight deployment that way. Seed the
  state you need directly instead — see
  `test_deploy_is_rejected_while_another_deployment_is_active`.
- **Reset the shared login rate limiter** in fixtures that hit `/auth/login`, or
  attempts leak between tests.
- Prefer testing a service function directly over an HTTP round trip when the
  behaviour is not about HTTP.

Frontend tests use vitest with jsdom. Pure logic — the SSE frame reducer, the
API client's error normalisation, the bootstrap generators — is the highest
value to cover, and none of it needs a rendered component.

## Migrations

```bash
cd backend
alembic revision -m "add something"    # then write upgrade() and downgrade() by hand
alembic upgrade head
alembic downgrade -1                   # always verify the downgrade works
```

Revision ids in this project are descriptive, not hashes
(e.g. `0004_add_server_known_host_key`), and `down_revision` chains them in
order.

Two rules:

1. **Write a real `downgrade()`.** CI runs `downgrade base` and will fail
   otherwise.
2. **A migration adding a constraint must first make existing data satisfy it.**
   Migration `0005` is the example: it marks leftover non-terminal deployments
   as failed before creating the partial unique index, because the index cannot
   be built while duplicates exist.

Model changes need a matching migration. Nothing auto-generates them here —
`Base.metadata.create_all` is used only in tests.

## Code style

Backend: ruff with a 110-column line length, targeting Python 3.11. Enabled rule
families and the deliberate exceptions are in `backend/pyproject.toml`. mypy is
configured but advisory in CI; new code should type-check cleanly.

Frontend: ESLint with `typescript-eslint` and `react-hooks`. TypeScript runs in
strict mode with `noUnusedLocals` and `noUnusedParameters`.

One convention that matters more than formatting: **comments should explain why,
not what.** The codebase has several places where the non-obvious choice is
documented in place — the two-layer concurrency guard, the local log sequence
counter, the host key trust-on-first-use step. Keep that up; delete comments that
merely restate the code.

## Where things go

| Adding | Goes in |
| --- | --- |
| A new endpoint | `app/api/v1/`, thin, delegating to a service |
| Business logic | `app/services/` |
| Config, crypto, cross-cutting concerns | `app/core/` |
| Anything touching SSH | `app/services/ssh_service.py`, nowhere else |
| A background operation | `app/workers/` |
| A new page | `frontend/src/pages/`, plus a route in `routes.ts` |
| API calls | `frontend/src/api/`, with types in `frontend/src/types/` |

## Pull requests

- Keep the diff focused; separate refactors from behaviour changes.
- Cover new behaviour with a test that would fail without the change.
- Update the relevant page in `docs/` in the same PR. Documentation drift is a
  bug.
- Note anything security-relevant explicitly in the description, especially
  changes to SSH handling, encryption, authentication, or the concurrency
  guards.
