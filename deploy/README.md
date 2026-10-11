# Hosting several clients on one VPS

One server runs every client. All clients share the **same code** (one Docker image, `ai2-bot`). Each client
has its **own folder** with its settings, documents, texts, prompt and database. This is the
[Twelve-Factor](https://12factor.net/config) "separate code from config" pattern.

```
Customer's WhatsApp ──► Meta ──► https://<client>.bot.yourdomain.com/webhook
                                              │  DNS: *.bot → VPS IP
                                              ▼
VPS ─ Caddy (HTTPS on 443, free Let's Encrypt certificates, routes by hostname)
        ├─► bot-clienta ── its own Postgres
        ├─► bot-clientb ── its own Postgres
        └─► ...
```

## What is shared and what is per client

| Shared (in the image, built from this repo) | Per client (`/opt/bots/clients/<id>/`) |
|---|---|
| All Python code in `app/` | `.env`: WhatsApp token, AI key, business name, passwords |
| Journey engine, RAG, AI calls, admin API | `knowledge/`: their FAQs, prices, PDFs |
| Default texts, journey and prompt (copied once per new client) | `locales/`: welcome and menu texts |
| | `flows/main.yaml`: menu flow |
| | `system_prompt.md`: AI tone and rules |
| | Postgres database (customers, leads, chats) |

A new image never touches a client's folder. A client only moves to new code when you deploy that version to it.
If one client needs a feature, add it to the shared code behind a setting that is off by default, and turn it on
in that client's `.env`. Don't fork the code per client.

## Server layout

```
/opt/bots/
  code/                 this repo (git clone)
  shared.env            BOT_DOMAIN, ACME_EMAIL, SMTP, backup settings
  current-tag           newest image version (written by build-image.sh)
  caddy/                Caddyfile + sites/<id>.caddy
  clients/<id>/         one folder per client
  backups/<id>/         nightly database dumps + folder archives
  archive/              removed clients
```

## Capacity

Each client uses about 300 MB RAM (app + Postgres); the AI runs at Groq/Anthropic, not on your server.

| VPS RAM | Clients |
|---|---|
| 2 GB | ~5 |
| 4 GB | ~10–12 |
| 8 GB | ~20–25 |

Check real use with `status.sh`. Upgrade the VPS plan when RAM stays above about 80%.

---

## 0. Oracle Cloud VM: extra steps

Everything below works on Oracle Cloud, with these differences:

- **Shape**: Ampere A1 (ARM) and AMD shapes both work. Python, Postgres and Caddy images are multi-arch, and the
  image is built on the server for its own CPU. Pick the **Ubuntu 24.04** image (not Oracle Linux).
- **Two firewalls.** Oracle blocks traffic both in the cloud network and inside the VM.
  - Cloud: Console → Networking → Virtual Cloud Networks → your VCN → Subnet → Security List → Add Ingress Rules:
    source `0.0.0.0/0`, TCP ports `80,443`; and a second rule, UDP port `443`.
  - Inside the VM: `setup-server.sh` detects Oracle's iptables rules and opens 80/443 there (it skips ufw, which
    doesn't work on top of Oracle's rules).
- **Root**: you log in as `ubuntu` (`ssh -i <key> ubuntu@<VM-IP>`), then run `sudo -i` before the commands below.
- **Public IP**: the default (ephemeral) IP survives reboots but is lost if the instance is terminated. Your DNS
  record points at it, so for client work reserve it: Instance → Attached VNICs → IPv4 addresses → edit → Reserved.
- **Always Free idle reclaim**: Oracle may reclaim Always Free instances that sit almost idle for 7 days.
  A bot with few messages can look idle. Upgrading the account to Pay As You Go (Always Free resources stay free)
  removes this risk, so do it before giving a client a live bot.

**Getting the code onto the VM** without a Git host (from PowerShell on your PC; `tar` is built into Windows):

```powershell
tar --exclude=.env --exclude=.venv --exclude=data --exclude=__pycache__ --exclude=.pytest_cache -czf ai2.tgz -C E:\Projects AI2
scp -i <key> ai2.tgz ubuntu@<VM-IP>:/tmp/
```
```bash
sudo mkdir -p /opt/bots/code && sudo tar -xzf /tmp/ai2.tgz -C /opt/bots/code --strip-components=1
```

Never upload your local `.env` (your own keys) or `data/` (your test database). With this method, ship code updates
by uploading a new archive and running `build-image.sh` (without `--pull`). A private GitHub repo is easier long term.

## 1. One-time server setup

Prerequisites: a VPS with Ubuntu 24.04, a domain, and this repo in a **private** Git repository.

```bash
ssh root@<VPS-IP>
git clone <your-private-repo-url> /opt/bots/code
bash /opt/bots/code/deploy/scripts/setup-server.sh
```

This installs Docker, a firewall (22/80/443 only), 2 GB swap and nightly backups, then builds the image. Then:

1. Edit `/opt/bots/shared.env`: `BOT_DOMAIN`, `ACME_EMAIL`, `SMTP_*` (Brevo free tier works).
2. At your domain registrar add one DNS record: **Type A, Name `*.bot`, Value `<VPS-IP>`**.
   Check from your PC: `nslookup test.bot.yourdomain.com` should show the VPS IP.
3. Start Caddy: `cd /opt/bots/caddy && docker compose up -d`

Security: use SSH keys and disable password login (`PasswordAuthentication no` in `/etc/ssh/sshd_config`).

## 2. Add a client

Do the Meta side first ([docs/client-onboarding.md](../docs/client-onboarding.md)), then:

```bash
S=/opt/bots/code/deploy/scripts
bash $S/new-client.sh sharma-sweets "Sharma Sweets"
nano /opt/bots/clients/sharma-sweets/.env                 # WhatsApp token, phone number ID, app secret, AI key
# copy the client's documents into /opt/bots/clients/sharma-sweets/knowledge/  (scp or WinSCP from your PC)
bash $S/deploy-client.sh sharma-sweets
```

`new-client.sh` generates strong passwords and secrets, picks the newest image version, writes the Caddy site, and
prints the **webhook URL and verify token** to paste into the client's Meta app (WhatsApp → Configuration →
Webhook, then subscribe to `messages`).

Client has its own domain? `new-client.sh sharma-sweets "Sharma Sweets" bot.sharmasweets.in` and ask them to add
an A record `bot` → your VPS IP at their registrar.

## 3. Day-to-day

| Task | Command (`S=/opt/bots/code/deploy/scripts`) |
|---|---|
| See all clients, versions, health, RAM | `bash $S/status.sh` |
| Client changed documents / texts / prompt / flow | edit files in their folder, then `bash $S/deploy-client.sh <id>` (re-indexes on start) |
| Re-index without a restart | `POST /admin/knowledge/reindex` in the admin API (`https://<domain>/docs`) |
| Logs | `docker compose -f /opt/bots/clients/<id>/docker-compose.yml logs -f app` |
| Ship a code update | `bash $S/build-image.sh --pull`, test with `bash $S/deploy-client.sh <one-id> <tag>`, then `bash $S/update-all.sh <tag>` |
| Roll back one client | `bash $S/deploy-client.sh <id> <previous-tag>` (`docker images ai2-bot` lists versions) |
| Backup now | `bash $S/backup.sh` (or `backup.sh <id>`) |
| Remove a client | `bash $S/remove-client.sh <id>` (final backup, then archive) |

Image versions look like `20261006-ab12cd3` (build date + git commit). Each client's `.env` has `IMAGE_TAG`, so
clients can run different versions while you roll out carefully.

## 4. Backups

`backup.sh` runs nightly at 02:30. For each client it saves a Postgres dump plus an archive of the client folder
to `/opt/bots/backups/<id>/`, and keeps 14 days (`BACKUP_KEEP_DAYS`). The folder archive contains `.env`
secrets, so keep backups private.

Off-server copy (recommended): create a Backblaze B2 bucket, run `rclone config` once on the server, and set
`RCLONE_REMOTE=b2:<bucket>` in `shared.env`. Also turn on your VPS provider's snapshot backups.

Restore a database:
```bash
gunzip -c /opt/bots/backups/<id>/db-<stamp>.sql.gz | \
  docker compose -f /opt/bots/clients/<id>/docker-compose.yml exec -T db psql -U bot bot
```

## 5. Monitoring

Add each `https://<client-domain>/health` to UptimeRobot (free). You get an email if a bot stops answering.

## Troubleshooting

| Symptom | Check |
|---|---|
| Meta "verify and save" fails | DNS points at the VPS? `curl https://<domain>/health` works? Verify token matches `.env`? |
| Certificate errors | `docker compose -f /opt/bots/caddy/docker-compose.yml logs caddy` (DNS must resolve before Caddy can get a certificate) |
| Bot doesn't answer | client logs: `401` = wrong app secret, `WhatsApp API error 401` = token expired/wrong |
| App won't start: "Set secure values" | a `change-me` value is left in the client's `.env` |
| Out of memory | `status.sh`; upgrade the VPS or move a client to a second server |
