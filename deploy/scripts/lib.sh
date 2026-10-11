#!/usr/bin/env bash
# Shared helpers for the deploy scripts. Layout on the server:
#   /opt/bots/code        this repo (git clone)
#   /opt/bots/shared.env  server-wide settings (from deploy/shared.env.example)
#   /opt/bots/caddy       Caddy config; sites/<client-id>.caddy per client
#   /opt/bots/clients/<client-id>/   one folder per client
#   /opt/bots/backups/<client-id>/   nightly backups
set -euo pipefail

BOTS_ROOT="${BOTS_ROOT:-/opt/bots}"
CODE_DIR="$BOTS_ROOT/code"
CLIENTS_DIR="$BOTS_ROOT/clients"
CADDY_DIR="$BOTS_ROOT/caddy"
BACKUP_DIR="$BOTS_ROOT/backups"
SHARED_ENV="$BOTS_ROOT/shared.env"
IMAGE_NAME="ai2-bot"

die() { echo "ERROR: $*" >&2; exit 1; }

# Read KEY from an env file without sourcing it (values may contain shell characters).
env_get() {
  local file="$1" key="$2"
  grep -E "^${key}=" "$file" 2>/dev/null | tail -n1 | cut -d= -f2- | sed -E 's/[[:space:]]+#.*$//; s/^[[:space:]]+|[[:space:]]+$//g'
}

# Set KEY=value in an env file, keeping any inline comment out of the way.
env_set() {
  local file="$1" key="$2" value="$3"
  if grep -qE "^${key}=" "$file"; then
    sed -i -E "s|^${key}=.*|${key}=${value}|" "$file"
  else
    echo "${key}=${value}" >> "$file"
  fi
}

valid_client_id() {
  [[ "$1" =~ ^[a-z0-9][a-z0-9-]{1,30}$ ]] || die "client id must be 2-31 chars: lowercase letters, digits, dashes (got '$1')"
}

client_dir() {
  local dir="$CLIENTS_DIR/$1"
  [[ -d "$dir" ]] || die "no client '$1' in $CLIENTS_DIR"
  echo "$dir"
}

list_clients() {
  find "$CLIENTS_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort
}

# docker compose for one client folder (project name = folder name, .env read from that folder).
dc() {
  local dir="$1"; shift
  docker compose -f "$dir/docker-compose.yml" "$@"
}

caddy_reload() {
  docker compose -f "$CADDY_DIR/docker-compose.yml" exec -T caddy caddy reload --config /etc/caddy/Caddyfile
}

wait_healthy() {
  local dir="$1" i status
  for i in $(seq 1 30); do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$(dc "$dir" ps -q app)" 2>/dev/null || true)
    [[ "$status" == "healthy" ]] && return 0
    sleep 2
  done
  echo "WARNING: app is not healthy yet - check: docker compose -f $dir/docker-compose.yml logs app" >&2
  return 1
}
