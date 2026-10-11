#!/usr/bin/env bash
# Build the shared bot image from /opt/bots/code. Tags it with a version and as :latest.
#   build-image.sh            build the code as it is
#   build-image.sh --pull     git pull first
# Running bots are NOT changed. Roll out with deploy-client.sh or update-all.sh.
source "$(dirname "$0")/lib.sh"

cd "$CODE_DIR"
if [[ "${1:-}" == "--pull" ]]; then
  git pull --ff-only
fi

rev=$(git rev-parse --short HEAD 2>/dev/null || echo nogit)
tag="$(date +%Y%m%d)-$rev"

docker build -t "$IMAGE_NAME:$tag" -t "$IMAGE_NAME:latest" .
echo "$tag" > "$BOTS_ROOT/current-tag"   # new clients start on this version
echo
echo "Built $IMAGE_NAME:$tag (also tagged :latest)"
echo "Roll out to one client first:  deploy-client.sh <client-id> $tag"
echo "Then to everyone:              update-all.sh $tag"
