# WhatsApp AI Chatbot: freelance delivery template

A production-ready WhatsApp chatbot built on the **WhatsApp Business Cloud API** and **Claude**. You can rebrand it
and ship it to a client in a day: swap the knowledge base, edit the journey YAML, set the env vars, and deploy.

| Feature | Where it lives |
|---|---|
| **AI LLM integration** (Claude Opus 5.5, refusal fallback, prompt caching) | `app/llm/claude.py`, `app/llm/groq.py` |
| **Retrieval-Augmented Generation**: answers grounded in the client's documents (MD / TXT / PDF) | `app/rag/`, `knowledge/` |
| **Pre-set conversational journey**: menus, buttons, forms, validation, branching, all in YAML | `app/journeys/flows/main.yaml` |
| **CRM / database integration**: local DB, HubSpot, or any webhook (Zapier / Make / n8n) | `app/crm/providers.py` |
| **User authentication**: email OTP links a WhatsApp number to a customer account; JWT-protected admin API | `app/auth/otp.py`, `app/admin/security.py` |
| **Multi-language**: English, Spanish, Hindi, Arabic out of the box; the AI replies in the user's language | `locales/*.yaml` |
| **Human handoff**: the bot goes quiet and an agent replies through the admin API | `handoff` node + `/admin/users/{id}/reply` |
| **Admin REST API**: conversations, leads, customers, knowledge upload/re-index (Swagger at `/docs`) | `app/admin/routes.py` |

---

## How it works

```
WhatsApp user ──► Meta Cloud API ──► POST /webhook  (signature verified, 200 returned immediately)
                                          │  background task
                                          ▼
                              conversation.process_incoming
                       dedupe → user lookup → handoff? → JourneyEngine
                                          │
          ┌───────────────┬───────────────┼────────────────┬──────────────────┐
          ▼               ▼               ▼                ▼                  ▼
     menu / input     ai node         action:            action:            action:
     (YAML flow)    RAG + Claude    crm.create_lead   auth.send/verify_otp  handoff.start
                         │                │                │
                  BM25 / Chroma      Local / HubSpot   Email OTP (SMTP)
                  over knowledge/    / Webhook CRM
                                          │
                     replies ──► WhatsApp Cloud API (text, buttons, lists)
```

### The default journey

```
first message ─► Language list ─► Welcome ─► Main menu ─┬─ Ask a question ─► AI chat (RAG), stays until "menu"
                                                        ├─ Book a demo ────► name → email → interest → CRM lead
                                                        ├─ My account ─────► [OTP if needed] → account summary
                                                        ├─ Talk to a human ► handoff (bot silent until "bot")
                                                        └─ Change language
Typing a question at the menu goes straight to the AI.
Global keywords work everywhere: menu · language · human · logout (plus translations)
```

---

## Quick start (5 minutes, no WhatsApp account needed)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                 # add GROQ_API_KEY (or ANTHROPIC_API_KEY with LLM_PROVIDER=claude)

python scripts/chat_cli.py           # chat with the bot in your terminal
python scripts/chat_cli.py --offline # no API key: AI replies show the retrieved RAG excerpts
pytest                               # full test suite, no network needed
```

In the simulator you can tap buttons by typing their number. OTP codes are printed to the log. Demo customers
are `jane@example.com` and `raj@example.com`.

### Run the server

```bash
uvicorn app.main:app --reload
```

- `GET /health` returns a health check
- `GET|POST /webhook` is the WhatsApp webhook
- `/docs` is the Swagger UI for the admin API (`POST /admin/login` with `ADMIN_USERNAME` / `ADMIN_PASSWORD`)

If `WHATSAPP_TOKEN` is not set, replies are printed to the console, so you can test with curl before connecting Meta.

### Connect WhatsApp

Follow **[docs/whatsapp-setup.md](docs/whatsapp-setup.md)**. In short: create a Meta app, add WhatsApp, copy the
token and phone number ID into `.env`, expose your server over HTTPS (ngrok for dev), and register
`https://<host>/webhook` with your `WHATSAPP_VERIFY_TOKEN`.

### Deploy

**Several clients on one VPS (recommended):** follow **[deploy/README.md](deploy/README.md)**. One shared image,
one folder per client (settings, documents, texts, prompt, database), Caddy for HTTPS, plus scripts to add,
update, back up and remove clients.

**Single deployment (local test or one client):**

```bash
docker compose up -d --build    # app + PostgreSQL
```

Set `ENVIRONMENT=production` for real traffic. The app then refuses to start with default secrets, rejects
unsigned webhooks, and requires SMTP for OTP.

---

## Delivering to a client

| Guide | What it covers |
|---|---|
| [docs/client-onboarding.md](docs/client-onboarding.md) | Step by step: Meta account, phone number, credentials, content, testing, handover |
| [deploy/README.md](deploy/README.md) | Hosting all clients on one VPS: setup, add/update/remove clients, backups |
| [docs/customization.md](docs/customization.md) | Editing the journey, texts, languages, CRM, AI prompt |
| [docs/services-and-costs.md](docs/services-and-costs.md) | Every external service, who pays, current prices |
| [docs/commercial-terms.md](docs/commercial-terms.md) | Managed service vs licence vs buyout, contract checklist |

**Shared code vs client files.** Code in `app/` is the same for every client. Everything client-specific lives
outside it and is set per deployment:

| Client-specific | Setting | Default in this repo |
|---|---|---|
| Secrets, business name, AI provider, CRM | `.env` | `.env.example` |
| Documents | `KNOWLEDGE_DIR` | `knowledge/` (sample) |
| Welcome and menu texts | `LOCALES_DIR` | `locales/` |
| Menu flow | `JOURNEY_FILE` | `app/journeys/flows/main.yaml` |
| AI tone and rules | `SYSTEM_PROMPT_FILE` | `prompts/system_prompt.md` |

If one client needs a new feature, add it to the shared code behind a setting that is off by default.

---

## Project structure

```
app/
  main.py                 FastAPI app, startup (DB, demo seed, knowledge indexing)
  config.py               all settings (env / .env)
  models.py               User, Message, Customer, Lead, OtpCode, DocumentChunk
  whatsapp/               webhook (verify + signature), payload parser, Cloud API client
  journeys/               YAML journey engine, actions, flows/main.yaml
  llm/                    Claude / Groq clients + RAG assistant (prompting, memory)
  rag/                    chunking/ingestion, BM25 + Chroma retrievers
  crm/                    Local / HubSpot / Webhook providers
  auth/                   email OTP verification
  admin/                  JWT auth + admin REST API
  services/               service container, message orchestrator
locales/                  en / es / hi / ar strings
knowledge/                sample knowledge base (replace per client)
prompts/                  system_prompt.md: default AI tone and rules (copied per client)
scripts/                  chat_cli.py (terminal simulator), ingest.py
tests/                    pytest suite (journey, auth, RAG, webhook, admin, Claude request shape)
deploy/                   multi-client VPS hosting: client template, Caddy, management scripts
docs/                     WhatsApp setup, client onboarding, customization, costs, commercial terms
```

## Configuration reference

All settings are in `.env.example`, with defaults in `app/config.py`. The ones you'll touch most:

| Variable | Purpose |
|---|---|
| `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` | Cloud API credentials |
| `WHATSAPP_VERIFY_TOKEN` | Your chosen string for webhook verification |
| `WHATSAPP_APP_SECRET` | Verifies `X-Hub-Signature-256` on every webhook (required in production) |
| `LLM_PROVIDER` | `groq` or `claude` (default `claude`) |
| `GROQ_API_KEY`, `GROQ_MODEL` | Groq credentials and model (default `openai/gpt-oss-120b`) |
| `ANTHROPIC_API_KEY`, `LLM_MODEL` | Claude credentials and model (default `claude-opus-5-5`) |
| `LLM_EFFORT` | `low` (fast and cheap, the default for chat) up to `high` for complex domains |
| `LLM_FALLBACKS` | Server-side refusal fallback. Keep `true` on the Claude API; set `false` on Bedrock, Vertex or Foundry |
| `RAG_BACKEND` | `bm25` (no extra dependencies) or `chroma` (semantic vectors, `pip install chromadb`) |
| `CRM_PROVIDER` | `local`, `hubspot` or `webhook` |
| `SMTP_*` | Sends OTP emails. When empty in development, codes are logged instead |
| `DATABASE_URL` | SQLite by default, `postgresql+psycopg://...` in production |
| `KNOWLEDGE_DIR`, `LOCALES_DIR`, `JOURNEY_FILE`, `SYSTEM_PROMPT_FILE` | Where the client's documents, texts, flow and AI prompt are read from |
| `RAG_REINDEX_ON_STARTUP` | `true` re-reads `KNOWLEDGE_DIR` on every start, so edited documents apply after a restart |

## AI and RAG details

- **Model:** Claude Opus 5.5 with adaptive thinking. Effort is set explicitly (`LLM_EFFORT`) and defaults to `low`
  so WhatsApp replies arrive quickly.
- **Grounding:** each question retrieves the top-k chunks (`RAG_TOP_K`). Chunks are section-aware: each one is
  prefixed with `Document › Section`, so retrieval and the model both know where it came from. The model is told to
  answer only from these excerpts and to offer *human* when they don't cover the question.
- **Memory:** the last `LLM_HISTORY_TURNS` AI exchanges are sent as conversation history.
- **Prompt caching:** the system prompt is static and marked with `cache_control`. Per-request data (excerpts,
  language) goes in the user turn so the cached prefix never changes. Caching only applies once the system prompt
  is longer than the model's minimum cacheable size, which a long client-specific prompt will reach.
- **Safety:** `stop_reason == "refusal"` is handled with a friendly message. When `LLM_FALLBACKS=true`, the API
  first retries a declined request on a fallback model server-side (`fallbacks: "default"`).
- **Failures:** rate limits, API errors and network errors become a localized "assistant unavailable" message.
  The bot never goes silent.
- **BM25 or vectors:** BM25 works well for FAQ-style content and needs no embedding service. For large or
  paraphrase-heavy corpora, use `RAG_BACKEND=chroma`. Retrievers share one interface, so pgvector, Pinecone and
  others are a single class each.

## Security notes

- Webhook payloads are verified with HMAC-SHA256 (`WHATSAPP_APP_SECRET`), and duplicate deliveries are ignored
  through a unique message ID.
- OTP codes are random, stored only as HMAC hashes, expire after `OTP_TTL_MINUTES`, lock out after
  `OTP_MAX_ATTEMPTS` tries, and are single-use.
- The admin API uses short-lived HS256 JWTs. Production mode refuses to start with default secrets.
- The system prompt tells the model never to ask for passwords, card numbers or codes.
- Messages from one user are processed in order (per-user lock). If you run several workers, use sticky routing
  or replace the lock with Redis.

## Known limits and next steps

- WhatsApp only allows free-form messages within **24 hours** of the user's last message. Proactive messages
  (reminders, broadcasts) need approved **template messages**. Add a `send_template` method to `WhatsAppClient`
  if the client needs them.
- Voice notes and images get a "text only" reply. You can add transcription or Claude vision in
  `conversation.py`.
- There are no DB migrations yet (`create_all` runs at startup). Add Alembic before the first schema change in
  production.
