#!/usr/bin/env bash
# Stop a client and take it offline:  remove-client.sh <client-id>
# Makes a final backup and moves the folder to /opt/bots/archive. The database volume is kept
# until you delete it yourself (the command is printed at the end).
source "$(dirname "$0")/lib.sh"

id="${1:-}"
[[ -n "$id" ]] || die "usage: remove-client.sh <client-id>"
dir=$(client_dir "$id")

read -r -p "Stop and archive '$id' ($(env_get "$dir/.env" CLIENT_DOMAIN))? Type the client id to confirm: " answer
[[ "$answer" == "$id" ]] || die "cancelled"

bash "$CODE_DIR/deploy/scripts/backup.sh" "$id"
dc "$dir" down
rm -f "$CADDY_DIR/sites/$id.caddy"
caddy_reload >/dev/null 2>&1 || true

mkdir -p "$BOTS_ROOT/archive"
mv "$dir" "$BOTS_ROOT/archive/$id-$(date +%Y%m%d)"

cat <<EOF
'$id' is offline. Final backup: $BACKUP_DIR/$id
Folder archived to $BOTS_ROOT/archive/. To delete its database for good:
  docker volume rm ${id}_pgdata ${id}_appdata
Remember: remove yourself from the client's Meta Business portfolio and hand over their data export.
EOF
