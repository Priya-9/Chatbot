# Onboarding a new client

The client **owns** their Meta account, WhatsApp number, billing and API keys. You get partner access to build and
run the bot. If the client ever leaves, they keep their number and data. You keep your software.

## 0. Before you start: agree on

- [ ] Offering: managed service, licence, or buyout (see [commercial-terms.md](commercial-terms.md))
- [ ] Setup fee, monthly fee, and that **Meta messaging and AI usage are billed to the client directly**
- [ ] Which phone number the bot will use (see step 2)
- [ ] Languages, menu options, and whether they need lead capture, "My account" (OTP login) or human handoff
- [ ] Who on their team replies when a customer types *human*

## 1. Client: Meta Business account (they do this, you guide)

1. Create a business portfolio at <https://business.facebook.com>.
2. **Business verification**: Business settings → Security centre → Start verification. They need a GST
   certificate or business registration, plus a website or official document with the business name and address.
   Without verification, messaging limits stay low.
3. **Add you as a partner** (Business settings → Partners), or add you as a person with full control of the app
   and WhatsApp account.
4. **Payment method**: WhatsApp Manager → Payment settings → their own card. Meta bills them directly.

## 2. The phone number

A number can be connected to the WhatsApp **app** or to the **Cloud API**, not both, unless the client uses
coexistence (below).

| Option | What happens | When to use |
|---|---|---|
| **New number** (recommended) | Buy a new SIM (~₹200–300/month to keep active) and use it only for the bot. The client's old number keeps working on their phone. | Default. Market it as their "official WhatsApp support line". |
| **Move their existing number** | They delete the WhatsApp account on that number in the phone app (Settings → Account → Delete account). The bot then owns the number; chat history stays on the old phone. Staff reply through the admin API. | They want customers to keep using the number they already know. |
| **Coexistence** (same number in app + API) | Needs Meta's Embedded Signup through a Tech Provider or a BSP (Gupshup, Interakt, 360dialog). Not supported by the manual setup here. | Only if they must keep replying from the phone app. |

## 3. You: Meta app and credentials (inside the client's portfolio)

Detailed clicks are in [whatsapp-setup.md](whatsapp-setup.md). Summary:

1. <https://developers.facebook.com/apps> → Create app → Business → **pick the client's portfolio**.
2. Add product **WhatsApp**, then **Add phone number** and verify it by SMS or a call.
3. Set the **display name** (Meta approves it, usually within 1–2 days) and the profile picture and description.
4. **Permanent token**: Business settings → Users → System users → add an *Admin* system user → assign the app
   and the WhatsApp account → Generate token with `whatsapp_business_messaging` and
   `whatsapp_business_management`, expiry **Never**.
5. Copy into the client's `.env` on the server:

   | Meta value | `.env` key |
   |---|---|
   | System user token | `WHATSAPP_TOKEN` |
   | Phone number ID (WhatsApp → API Setup) | `WHATSAPP_PHONE_NUMBER_ID` |
   | App secret (App settings → Basic) | `WHATSAPP_APP_SECRET` |

6. AI key: the client creates a key at <https://console.groq.com> or <https://console.anthropic.com> (their card),
   or you use yours and bill it back. Put it in `GROQ_API_KEY` / `ANTHROPIC_API_KEY`.

Store every token and password in your password manager (e.g. Bitwarden) under the client's name.

## 4. You: content

Collect from the client:

- [ ] FAQs, price list, policies, menu or catalogue, opening hours, contact details (PDF, Word saved as PDF, or text)
- [ ] Welcome message and menu wording, in each language
- [ ] Rules for the AI: things it must never say (e.g. "never promise delivery dates", "no discounts")
- [ ] Logo and description for the WhatsApp profile

Put them in the client's folder on the server:

| Content | Where |
|---|---|
| Documents | `knowledge/` (`.md`, `.txt`, `.pdf`) |
| Welcome and menu texts | `locales/<lang>.yaml` |
| Menu flow, forms | `flows/main.yaml` ([customization.md](customization.md)) |
| AI tone and rules | `system_prompt.md` |
| Business name, languages, CRM | `.env` |

Test the content on your PC first with `python scripts/chat_cli.py` by pointing `KNOWLEDGE_DIR`,
`LOCALES_DIR`, `JOURNEY_FILE` and `SYSTEM_PROMPT_FILE` at a copy of the client's files.

## 5. You: deploy

Follow [deploy/README.md](../deploy/README.md) → "Add a client". Then, in the client's Meta app → WhatsApp →
Configuration → Webhook: paste the callback URL and verify token that `new-client.sh` printed, **Verify and save**,
and subscribe to **messages**.

## 6. Test before go-live

- [ ] "hi" from a phone that is not an admin → language list, then welcome
- [ ] 5–10 real customer questions → answers come from their documents; unknown questions → "type *human*"
- [ ] Each menu option and form works; a test lead arrives in their CRM / sheet
- [ ] *human* → bot goes silent; an agent reply through the admin API reaches the phone; *bot* resumes
- [ ] OTP email arrives (only if "My account" is used)
- [ ] `https://<domain>/health` added to UptimeRobot

## 7. Handover to the client

Give them:

- Admin API URL (`https://<domain>/docs`), username and password, for human handoff and viewing leads
- How to send you document updates, and how quickly you apply them
- What is billed by whom: Meta (their card), AI (their key), your monthly fee
- Support contact and hours

## Costs to explain up front (India, October 2026)

- Meta charges for **every bot reply** after **1,000 free service messages per number per month**:
  about ₹0.115 + 18% GST per message. Menus and buttons count as messages.
- Marketing broadcasts cost about ₹0.86 per message. Utility and authentication templates cost about ₹0.115.
- AI: Groq costs about ₹0.06 per answer; Claude costs roughly ₹1–2 per answer depending on the model.

Full list: [services-and-costs.md](services-and-costs.md).
