#!/usr/bin/env bash
# One-time VPS setup (Ubuntu 22.04/24.04, run as root):
#   git clone <your-private-repo> /opt/bots/code
#   bash /opt/bots/code/deploy/scripts/setup-server.sh
source "$(dirname "$0")/lib.sh"

[[ $EUID -eq 0 ]] || die "run as root"
[[ -d "$CODE_DIR/app" ]] || die "clone the repo to $CODE_DIR first"

# Oracle Cloud Ubuntu images ship their own iptables rules (/etc/iptables/rules.v4) that reject everything except
# SSH. ufw would sit behind those rules and its ports would stay closed, so on Oracle we open ports in iptables.
oracle_fw=false
grep -qs -- '-j REJECT' /etc/iptables/rules.v4 && oracle_fw=true

echo "==> Packages"
apt-get update -q
apt-get install -y -q curl git cron rclone
$oracle_fw || apt-get install -y -q ufw

# Before Docker, so netfilter-persistent doesn't save Docker's own chains into rules.v4.
echo "==> Firewall: SSH, HTTP, HTTPS only"
if $oracle_fw; then
  # Insert just before Oracle's REJECT rule; skip if already there so re-runs are safe.
  for rule in "-p tcp --dport 80" "-p tcp --dport 443" "-p udp --dport 443"; do
    iptables -C INPUT $rule -m state --state NEW -j ACCEPT 2>/dev/null && continue
    pos=$(iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" {print $1; exit}')
    iptables -I INPUT "${pos:-1}" $rule -m state --state NEW -j ACCEPT
  done
  netfilter-persistent save
  echo "    Oracle Cloud: also open TCP 80, 443 and UDP 443 in the VCN Security List (see deploy/README.md)"
else
  ufw allow OpenSSH
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw allow 443/udp
  ufw --force enable
fi

if ! command -v docker >/dev/null; then
  echo "==> Docker"
  curl -fsSL https://get.docker.com | sh
fi

# Small VPSes have little RAM; swap stops a memory spike from killing a client's bot.
if ! swapon --show | grep -q .; then
  echo "==> 2 GB swap"
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "==> Folders"
mkdir -p "$CLIENTS_DIR" "$BACKUP_DIR" "$CADDY_DIR/sites"
[[ -f "$SHARED_ENV" ]] || { cp "$CODE_DIR/deploy/shared.env.example" "$SHARED_ENV"; chmod 600 "$SHARED_ENV"; }
cp "$CODE_DIR/deploy/caddy/Caddyfile" "$CODE_DIR/deploy/caddy/docker-compose.yml" "$CADDY_DIR/"

docker network inspect web >/dev/null 2>&1 || docker network create web

echo "==> Building the bot image"
bash "$CODE_DIR/deploy/scripts/build-image.sh"

echo "==> Nightly backups at 02:30"
cat > /etc/cron.d/ai2-bots-backup <<EOF
30 2 * * * root bash $CODE_DIR/deploy/scripts/backup.sh >> /var/log/ai2-backup.log 2>&1
EOF

cat <<EOF

Server ready. Next:
  1. Edit $SHARED_ENV  (BOT_DOMAIN, ACME_EMAIL, SMTP_*)
  2. DNS: add an A record  *.bot -> $(curl -fsS https://api.ipify.org || echo '<this server IP>')
  3. Start Caddy:  cd $CADDY_DIR && docker compose up -d
  4. Add a client: bash $CODE_DIR/deploy/scripts/new-client.sh <client-id> "<Business Name>"
EOF
