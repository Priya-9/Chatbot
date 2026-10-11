# Selling the service: offerings and contract checklist

This is a checklist, not legal advice. Have a lawyer turn it into your standard agreement once, then reuse it.

## Offerings

| | A. Managed service (default) | B. Licence + source code | C. Buyout |
|---|---|---|---|
| Client gets | A working bot, hosted and maintained by you | Code to run **only for their own business** | Copyright to the code |
| You keep | The code | Ownership of the code | Nothing (it's sold) |
| Price | Setup fee + monthly fee | Several times the setup fee, + optional support | Very high, a price you're glad to accept |
| Risk to you | Lowest | Medium, controlled by the contract | You lose control |

Put all three on your price sheet. Most clients choose A once they see the others.

## What the client always owns (write it in)

- Their **Meta account, WhatsApp number and API keys** (already in their name)
- Their **data**: documents, customer list, chat history, leads. Exported on request as a database dump + files.
- Their **content**: knowledge files, texts, journey and prompt written for them

## Managed service (A): clauses

- [ ] Scope: what's included (hosting, monitoring, updates, N knowledge updates/month) and what's extra (new features, new integrations)
- [ ] Fees: setup, monthly, payment terms, price changes with notice
- [ ] Meta and AI usage are billed to the client directly
- [ ] Support hours and response times
- [ ] Data ownership and export on request (above)
- [ ] Exit: either side can end with N days' notice; you provide a data export; you remove your access
- [ ] If you stop the service: 60–90 days' notice + export. Optional **source code escrow**: code released to them only if you stop supporting them.
- [ ] Liability limit (e.g. capped at fees paid in the last 3–12 months); AI answers may contain mistakes
- [ ] Confidentiality and data protection: you handle their customers' data only to run the service (DPDP Act 2023)

## Licence (B): extra clauses

- [ ] **Licence, not sale**: you keep all IP; they get a non-exclusive, non-transferable licence for their own business only
- [ ] **No resale**: no reselling, sublicensing, white-labelling or offering it as a service to others
- [ ] **No sharing**: no giving the code to other companies; no publishing it
- [ ] Their customizations (content, prompts, flows) are theirs; the core engine stays yours
- [ ] Liquidated damages (a fixed sum) for breach of the no-resale clause
- [ ] Support and updates are separate and optional

In India, software is protected as a literary work under the Copyright Act 1957, and restrictions on using the
licensed code are enforceable as contract terms. A general ban on the client working in the chatbot business after
the contract ends is usually not enforceable (Contract Act, section 27). Restrict use of **your code**, not their
business.

## Practical protection

- Hand over only what they paid for: the deployed version, not your repo, deploy scripts for other clients or future features
- Keep the `LICENSE` file and copyright notice in the code
- Your edge is the service: Meta onboarding, prompt tuning, quick fixes and ongoing improvements
