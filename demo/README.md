# Sales demo

A public WhatsApp demo for finding clients. The bot first asks **what kind of business the visitor runs**, then
plays a realistic sample business in that niche, so every prospect sees the bot working for *their* trade.

```
hi ─► language ─► "What kind of business do you run?" (10 niches) ─► welcome as e.g. "Glow Studio Unisex Salon"
                                                                   │   + 3 example questions to try
                                                                   ▼
          Ask a question (AI, answers only from that niche's files)
          Book a slot / Reserve a table / Book a site visit…  → saved as a lead "[DEMO BOOKING] …"
          Talk to a human                                     → you take over the chat
          Get this bot 🚀                                     → name + business → lead "[PROSPECT] …"
          Try another business                                → back to the niche list
```

Keywords anywhere: `menu`, `switch` (pick another niche), `human`, `get bot`, `language`.

## Run it

```bash
python scripts/chat_cli.py --demo --offline   # no API key needed
python scripts/chat_cli.py --demo             # real AI answers
```

For WhatsApp, copy the settings from `.env.demo.example` into `.env`. Set `BUSINESS_NAME` to **your own
brand**, because it appears in "built by …" and in the pitch.

## Edit the content (no code)

| What | File |
|---|---|
| Niche list, sample business names, booking questions, example questions | `demo/niches.yaml` |
| What each sample business knows (prices, timings, FAQ) | `demo/knowledge/<niche>/*.md` |
| Bot texts: welcome, pitch, booking confirmation (en / hi / es / ar) | `locales/<lang>.yaml`, `demo:` section |
| AI tone and rules | `demo/system_prompt.md` |
| Menu and steps | `app/journeys/flows/demo.yaml` |

To add a niche, add an entry to `niches.yaml` and a folder `demo/knowledge/<id>/` with one Markdown file.
WhatsApp lists show at most 10 rows, so replace a niche rather than adding an 11th. Run `pytest
tests/test_demo.py` afterwards; it checks titles fit WhatsApp's limits and that every niche has knowledge.

## Get the leads

Set `CRM_PROVIDER=webhook` and `CRM_WEBHOOK_URL` to a Zapier / Make / n8n hook that appends a row to a Google
Sheet (and notifies you). `[PROSPECT]` rows are people who want a bot; `[DEMO BOOKING]` rows are test
bookings. Showing that sheet in your video is the most convincing moment.

## Client deployments are unaffected

Nothing here changes the client template. `app/journeys/flows/main.yaml` (with OTP login, My account, etc.),
`knowledge/` and `prompts/system_prompt.md` work exactly as before, and every action stays available to any
client's flow. The new `niche_select` node and the optional `create_lead` options (`name_field`, `interest`,
`thanks`…) can be used in client flows too.
