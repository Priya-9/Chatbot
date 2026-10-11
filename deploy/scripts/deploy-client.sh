#!/usr/bin/env bash
# Start a client, or move it to another image version:
#   deploy-client.sh <client-id>            (re)start on the version in its .env
#   deploy-client.sh <client-id> <tag>      switch to that version (also how you roll back)
source "$(dirname "$0")/lib.sh"

id="${1:-}"; tag="${2:-}"
[[ -n "$id" ]] || die "usage: deploy-client.sh <client-id> [image-tag]"
dir=$(client_dir "$id")

if [[ -n "$tag" ]]; then
  docker image inspect "$IMAGE_NAME:$tag" >/dev/null 2>&1 || die "no image $IMAGE_NAME:$tag (see: docker images $IMAGE_NAME)"
  env_set "$dir/.env" IMAGE_TAG "$tag"
fi

echo "==> $id on $IMAGE_NAME:$(env_get "$dir/.env" IMAGE_TAG)"
dc "$dir" up -d --remove-orphans
caddy_reload >/dev/null 2>&1 || echo "NOTE: Caddy not running - start it: cd $CADDY_DIR && docker compose up -d"

if wait_healthy "$dir"; then
  echo "OK: https://$(env_get "$dir/.env" CLIENT_DOMAIN)/health"
fi
