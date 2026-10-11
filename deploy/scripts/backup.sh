#!/usr/bin/env bash
# Back up every client (or one):  backup.sh [client-id]
# Per client: database dump + its folder (.env, knowledge, locales, flows, prompt).
# setup-server.sh runs this nightly from cron. Set RCLONE_REMOTE in shared.env to copy off the server.
source "$(dirname "$0")/lib.sh"

keep_days=$(env_get "$SHARED_ENV" BACKUP_KEEP_DAYS); keep_days=${keep_days:-14}
remote=$(env_get "$SHARED_ENV" RCLONE_REMOTE)
stamp=$(date +%Y%m%d-%H%M)
ids=${1:-$(list_clients)}

for id in $ids; do
  dir=$(client_dir "$id")
  out="$BACKUP_DIR/$id"
  mkdir -p "$out" && chmod 700 "$out"
  echo "==> $id"
  if dc "$dir" ps -q db | grep -q .; then
    dc "$dir" exec -T db pg_dump -U bot --clean --if-exists bot | gzip > "$out/db-$stamp.sql.gz"
  else
    echo "  database not running - skipped dump"
  fi
  tar -czf "$out/files-$stamp.tar.gz" -C "$CLIENTS_DIR" "$id"   # includes .env secrets: keep backups private
  find "$out" -type f -mtime +"$keep_days" -delete
done

if [[ -n "$remote" ]]; then
  echo "==> Copying to $remote"
  rclone copy "$BACKUP_DIR" "$remote" --max-age 25h
fi
echo "Backups in $BACKUP_DIR"

# Restore a database:
#   gunzip -c db-<stamp>.sql.gz | docker compose -f /opt/bots/clients/<id>/docker-compose.yml exec -T db psql -U bot bot
