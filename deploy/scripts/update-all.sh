#!/usr/bin/env bash
# Move every client to one image version (default: the newest build):
#   update-all.sh [tag]
# Test the tag on one client first with deploy-client.sh.
source "$(dirname "$0")/lib.sh"

tag="${1:-$(cat "$BOTS_ROOT/current-tag" 2>/dev/null || true)}"
[[ -n "$tag" ]] || die "no tag given and no $BOTS_ROOT/current-tag - run build-image.sh"

failed=()
for id in $(list_clients); do
  bash "$CODE_DIR/deploy/scripts/deploy-client.sh" "$id" "$tag" || failed+=("$id")
done

if (( ${#failed[@]} )); then
  echo "Needs attention: ${failed[*]}"
  exit 1
fi
echo "All clients on $IMAGE_NAME:$tag"
