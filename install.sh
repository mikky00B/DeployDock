#!/usr/bin/env bash
#
# DeployDock installer (v3 spec §4.4).
#
#   ./install.sh                                   # from a checkout
#   curl -fsSL <hosted install.sh URL> | bash      # one-line install
#
# Checks prerequisites (Docker, Compose), writes backend/.env with generated
# secrets (never overwriting an existing one), and brings the stack up with
# `docker compose up -d --build`.
#
# Environment overrides: DEPLOYDOCK_DIR (clone destination, default
# ./deploydock), DEPLOYDOCK_BRANCH (default master), DEPLOYDOCK_NO_CLONE=1
# (require an existing checkout).
set -euo pipefail

REPO_URL="https://github.com/mikky00B/DeployDock.git"
BRANCH="${DEPLOYDOCK_BRANCH:-master}"

log() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1; }

generate_secret() {
    # 64-byte secrets for SECRET_KEY / ENCRYPTION_KEY (spec §29).
    if need_cmd python3; then
        python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
    elif need_cmd openssl; then
        openssl rand -hex 64
    else
        fail "python3 or openssl is needed to generate secrets"
    fi
}

# --- Run from a checkout: when piped, clone first and restart in place. ------
if [ ! -f docker-compose.yml ]; then
    if [ "${DEPLOYDOCK_NO_CLONE:-0}" = "1" ] || [ -t 0 ]; then
        fail "no docker-compose.yml here — run from a DeployDock checkout, or pipe the script: curl -fsSL <url> | bash"
    fi
    need_cmd git || fail "git is required to download DeployDock"
    log "Cloning DeployDock (${BRANCH})..."
    dest="${DEPLOYDOCK_DIR:-deploydock}"
    if [ -d "$dest/.git" ]; then
        log "$dest already cloned — pulling latest..."
        git -C "$dest" fetch --depth 1 origin "$BRANCH"
        git -C "$dest" reset --hard "origin/$BRANCH"
    else
        git clone --depth 1 -b "$BRANCH" "$REPO_URL" "$dest"
    fi
    cd "$dest"
    exec bash install.sh
fi

# --- Prerequisites. ----------------------------------------------------------
need_cmd docker || fail "Docker is required: https://docs.docker.com/engine/install/"
if docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose"
elif need_cmd docker-compose; then
    COMPOSE="docker-compose"
else
    fail "Docker Compose is required (the 'docker compose' plugin or docker-compose)"
fi
docker info >/dev/null 2>&1 || fail "the Docker daemon is not running — start Docker first"

# --- Secrets. -----------------------------------------------------------------
if [ -f backend/.env ]; then
    log "backend/.env already exists — keeping it (delete it to regenerate secrets)"
else
    log "Writing backend/.env with generated secrets..."
    secret_key="$(generate_secret)"
    encryption_key="$(generate_secret)"
    cp backend/.env.example backend/.env
    sed -i.bak \
        -e "s|^SECRET_KEY=.*|SECRET_KEY=${secret_key}|" \
        -e "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=${encryption_key}|" \
        backend/.env
    rm -f backend/.env.bak
fi

# --- Bring the stack up. ------------------------------------------------------
log "Building and starting the stack (this can take a few minutes on first run)..."
$COMPOSE up -d --build

log "Waiting for the API to become healthy..."
for _ in $(seq 1 60); do
    if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
        break
    fi
    sleep 2
done
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
    fail "the API did not become healthy within 2 minutes — check: $COMPOSE logs api"
fi

cat <<'EOF'

  DeployDock is up.

    Dashboard:  http://127.0.0.1:5173
    API:        http://127.0.0.1:8000
    API docs:   http://127.0.0.1:8000/docs

  Next steps:
    - Open the dashboard and create your account.
    - Before exposing DeployDock beyond localhost, follow the production
      guardrails in docs/configuration.md (APP_ENV=production, real CORS
      origins, TLS in front of both ports).
EOF
