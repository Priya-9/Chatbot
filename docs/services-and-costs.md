# External services and costs

Prices checked in October 2026 (€1 ≈ ₹100, $1 ≈ ₹88). They change, so recheck before buying.

## You (shared by all clients)

| Service | Purpose | Recommended | Cost | Required |
|---|---|---|---|---|
| VPS | Runs every client's bot | Hetzner CX23 (4 GB) · or Hostinger KVM 1 (UPI, GST invoice) | ~₹460/month · ₹599 intro → ₹999 renewal | Yes |
| Domain + DNS | `*.bot.yourdomain.com` for all clients | Cloudflare Registrar (same price at renewal) · Namecheap | ~₹900/year | Yes (free for testing: DuckDNS, sslip.io) |
| Let's Encrypt | HTTPS certificates (Caddy gets them automatically) | n/a | Free | Yes |
| GitHub (private repo) | Your code; the server pulls updates | github.com | Free | Yes |
| Docker Hub / PyPI | Base images and Python packages, downloaded during build | n/a | Free | Yes |
| SMTP email | OTP login codes | Brevo (300/day free) · Amazon SES | Free | If "My account" is used |
| Off-server backups | Copies of nightly dumps | Backblaze B2 + rclone | Free up to 10 GB | Strongly recommended |
| VPS snapshots | Restore the whole server | Provider's backup add-on | ~20% of VPS price | Recommended |
| Uptime monitoring | Email alert if a bot is down | UptimeRobot | Free | Recommended |
| Password manager | Every client's tokens and passwords | Bitwarden | Free | Recommended |
| ngrok | Local testing on your PC only | ngrok.com | Free tier | Optional |

**Your fixed cost:** about ₹625/month for 4–5 clients.

## Each client (in their own name)

| Service | Purpose | Cost |
|---|---|---|
| Meta Business portfolio + Developer app + WhatsApp Manager | WhatsApp Cloud API account, number, templates, billing | Free to set up |
| Meta messaging (India, + 18% GST) | Service replies: **1,000 free per number per month**, then ₹0.115 each (since 1 Oct 2026). Utility/auth templates ₹0.115. Marketing ₹0.86. | Usage |
| Phone number / SIM | The bot's number | ~₹200–300/month |
| AI provider | Answers questions | Groq `gpt-oss-120b` ~₹0.06/answer (cheapest, fast) · Claude: higher quality, roughly ₹1–2/answer |
| CRM (optional) | HubSpot (free tier), or Zapier / Make / n8n to Google Sheets or Zoho | Free tiers |

## Free software on the server

Ubuntu, Docker + Compose, Caddy, PostgreSQL 17, UFW firewall, Git, rclone, and the Python libraries in
`requirements.txt` (FastAPI, SQLAlchemy, Anthropic SDK, etc.).

## Example monthly bill for one client

About 1,500 conversations × 6 bot messages ≈ 9,000 messages, of which about 3,000 are AI answers:

| | Groq | Claude |
|---|---|---|
| Meta: (9,000 − 1,000 free) × ₹0.115 + GST | ~₹1,085 | ~₹1,085 |
| AI | ~₹180 | ~₹2,500 (Sonnet 5.5) to ~₹5,000 (Opus 5.5) |
| SIM | ~₹250 | ~₹250 |

Fewer messages per conversation lowers the Meta bill. Combine texts and avoid unnecessary menus.
