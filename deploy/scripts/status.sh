#!/usr/bin/env bash
# One line per client: version, health, URL. Then memory use per container.
source "$(dirname "$0")/lib.sh"

printf '%-22s %-22s %-10s %s\n' CLIENT VERSION HEALTH URL
for id in $(list_clients); do
  dir="$CLIENTS_DIR/$id"
  container=$(dc "$dir" ps -q app 2>/dev/null || true)
  health=$([[ -n "$container" ]] && docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo stopped)
  printf '%-22s %-22s %-10s %s\n' "$id" "$(env_get "$dir/.env" IMAGE_TAG)" "$health" "https://$(env_get "$dir/.env" CLIENT_DOMAIN)"
done
echo
free -h | head -2
echo
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}'
