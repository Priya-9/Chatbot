# Customizing the bot for a client

## Delivery checklist

On the server, every file below lives in the client's own folder (`/opt/bots/clients/<id>/`), not in the
shared code. See [deploy/README.md](../deploy/README.md) and [client-onboarding.md](client-onboarding.md).

- [ ] `BUSINESS_NAME` set; welcome and menu texts edited in every `locales/*.yaml`
- [ ] Client documents in `knowledge/`, then `python scripts/ingest.py`; spot-check answers with `scripts/chat_cli.py`
- [ ] `system_prompt.md` adjusted for tone and domain rules (e.g. "never quote delivery dates")
- [ ] Journey edited in `flows/main.yaml` (repo default: `app/journeys/flows/main.yaml`)
- [ ] CRM connected (`CRM_PROVIDER`) and a test lead confirmed in the client's CRM
- [ ] Customers imported (`POST /admin/customers`), or OTP lookup pointed at the client's CRM
- [ ] SMTP configured, and an OTP email received
- [ ] WhatsApp live number, permanent token, and webhook (see `whatsapp-setup.md`)
- [ ] `ENVIRONMENT=production`, strong secrets, PostgreSQL, HTTPS
- [ ] `pytest` passes after your changes

## Editing the journey

Every text value is a translation key. Add the key to each `locales/<lang>.yaml`.

```yaml
# Add a menu option
main_menu:
  options:
    - {id: track_order, label: menu.track, description: menu.track_desc, next: order_number}

# Ask for input with validation (nonempty | email | phone | otp, or add your own in engine.VALIDATORS)
order_number:
  type: input
  text: order.ask_number
  save_as: order_number
  validate: nonempty
  next: order_lookup

# Call Python code
order_lookup:
  type: action
  action: orders.lookup
  requires_auth: true        # users must verify by OTP first; afterwards they return here automatically
  on_success: main_menu
  on_failure: main_menu
```

Then register the action in `app/journeys/actions.py`:

```python
def lookup_order(ctx: Context, node: dict) -> ActionResult:
    number = ctx.data.get("order_number")
    order = my_client_api.get_order(number, customer=ctx.user.customer_ref)   # your integration
    if not order:
        return ActionResult(ok=False, messages=[TextOut(ctx.t("order.not_found"))])
    return ActionResult(messages=[TextOut(ctx.t("order.status", status=order.status))])

ACTIONS["orders.lookup"] = lookup_order
```

The engine checks the flow at startup. A typo in a node name or an unknown action fails immediately instead of
breaking mid-conversation.

Menus with 3 or fewer options are shown as **buttons**, and longer menus as a **list** (up to 10). Labels are
cut to WhatsApp's limits (20 characters for buttons, 24 for list rows).

## Adding a language

1. Copy `locales/en.yaml` to `locales/fr.yaml`, translate it, and set `_meta.name: Français` and
   `_meta.english_name: French`.
2. Set `SUPPORTED_LANGUAGES=en,es,hi,ar,fr`.
3. Optionally add French words to the `commands` and `resume_keywords` lists in the flow YAML.

`tests/test_rag_and_i18n.py::test_all_locales_have_the_same_keys` catches missing keys. Add the new code there.
The AI answers in the user's language automatically, even when the knowledge base is in English.

## Adding a CRM (Salesforce, Zoho, Pipedrive and others)

Implement the four methods of `CRMProvider` in `app/crm/providers.py`: `find_customer_by_email`, `get_customer`,
`create_lead` and `log_event`. Then add a branch in `build_crm()`. Use `HubSpotCRM` as the reference
implementation.

## Changing the LLM behavior

- **Tone and rules:** edit the client's `system_prompt.md` (`SYSTEM_PROMPT_FILE`; repo default
  `prompts/system_prompt.md`). `{business}` is replaced with `BUSINESS_NAME`. Keep it free of per-request data, which
  goes in `build_user_turn()`, so prompt caching keeps working.
- **Speed vs. depth:** `LLM_EFFORT=low|medium|high`.
- **Retrieval breadth:** `RAG_TOP_K`, `RAG_CHUNK_SIZE`.
- **Swap the provider:** anything with a `complete(system, messages) -> LLMResult` method works (see
  `app/llm/claude.py`).

## Swapping the retriever

Implement `search(query, k)` and `rebuild(chunks)` (see `app/rag/retriever.py`) for pgvector, Pinecone, Qdrant
or another store, then select it in `app/services/container.py`.
