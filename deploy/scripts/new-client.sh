#!/usr/bin/env bash
# Create a new client bot:
#   new-client.sh <client-id> "<Business Name>" [custom-domain]
# Example:
#   new-client.sh sharma-sweets "Sharma Sweets"                 -> sharma-sweets.<BOT_DOMAIN>
#   new-client.sh sharma-sweets "Sharma Sweets" bot.sharmasweets.in   (client points that DNS name at this server)
source "$(dirname "$0")/lib.sh"

id="${1:-}"; name="${2:-}"; custom_domain="${3:-}"
[[ -n "$id" && -n "$name" ]] || die "usage: new-client.sh <client-id> \"<Business Name>\" [custom-domain]"
valid_client_id "$id"
[[ -f "$SHARED_ENV" ]] || die "$SHARED_ENV missing - run setup-server.sh first"
dir="$CLIENTS_DIR/$id"
[[ ! -e "$dir" ]] || die "$dir already exists"

bot_domain=$(env_get "$SHARED_ENV" BOT_DOMAIN)
domain="${custom_domain:-$id.$bot_domain}"
[[ -n "$custom_domain" || ( -n "$bot_domain" && "$bot_domain" != "bot.yourdomain.com" ) ]] \
  || die "set BOT_DOMAIN in $SHARED_ENV (or pass a custom domain)"
tag=$(cat "$BOTS_ROOT/current-tag" 2>/dev/null || echo latest)

echo "==> Creating $dir"
mkdir -p "$dir/knowledge" "$dir/flows"
cp "$CODE_DIR/deploy/client-template/docker-compose.yml" "$dir/"
cp -r "$CODE_DIR/locales" "$dir/locales"
cp "$CODE_DIR/app/journeys/flows/main.yaml" "$dir/flows/main.yaml"
cp "$CODE_DIR/prompts/system_prompt.md" "$dir/system_prompt.md"
cat > "$dir/knowledge/README" <<'EOF'
Put this client's documents here (.md, .txt, .pdf): FAQs, price lists, policies, menus.
Then restart the bot to re-index:  bash /opt/bots/code/deploy/scripts/deploy-client.sh <client-id>
or without downtime: POST /admin/knowledge/reindex in the admin API.
(Only .md, .txt and .pdf files are indexed, so this README is skipped.)
EOF

secret() { openssl rand -hex "$1"; }
sed_escape() { printf '%s' "$1" | sed 's/[&|\\]/\\&/g'; }
sed -e "s|__CLIENT_ID__|$id|" \
    -e "s|__CLIENT_DOMAIN__|$(sed_escape "$domain")|" \
    -e "s|__BUSINESS_NAME__|$(sed_escape "$name")|" \
    -e "s|__DB_PASSWORD__|$(secret 16)|" \
    -e "s|__VERIFY_TOKEN__|$(secret 16)|" \
    -e "s|__ADMIN_PASSWORD__|$(secret 12)|" \
    -e "s|__JWT_SECRET__|$(secret 32)|" \
    "$CODE_DIR/deploy/client-template/.env.template" > "$dir/.env"
env_set "$dir/.env" IMAGE_TAG "$tag"
chmod 600 "$dir/.env"
chown -R 1000:1000 "$dir/knowledge"   # the bot runs as uid 1000 and saves admin uploads here

cat > "$CADDY_DIR/sites/$id.caddy" <<EOF
$domain {
	encode gzip
	reverse_proxy bot-$id:8000
}
EOF

cat <<EOF

Client '$id' created (not started yet). Next:
  1. Edit $dir/.env           WhatsApp token, phone number ID, app secret, AI key
  2. Add documents to          $dir/knowledge/
  3. Optional: edit            $dir/system_prompt.md, locales/, flows/main.yaml
  4. Start it:                 bash $CODE_DIR/deploy/scripts/deploy-client.sh $id
  5. In the client's Meta app → WhatsApp → Configuration → Webhook:
       Callback URL:  https://$domain/webhook
       Verify token:  $(env_get "$dir/.env" WHATSAPP_VERIFY_TOKEN)
     and subscribe to the 'messages' field.
  Admin API: https://$domain/docs   user: admin   password: $(env_get "$dir/.env" ADMIN_PASSWORD)
EOF
