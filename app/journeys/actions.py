"""Python actions callable from the journey YAML (`type: action`, `action: <name>`).

Add your own by writing a function `(ctx, node) -> ActionResult` and registering it in `ACTIONS`.
"""

from app.auth.otp import VerifyResult, mask_email
from app.crm.providers import LeadData
from app.i18n.translator import _SafeDict
from app.journeys.engine import ActionResult, Context
from app.models import Lead
from app.whatsapp.messages import TextOut


def create_lead(ctx: Context, node: dict) -> ActionResult:
    """Save a lead from collected journey data. Node options (all optional, defaults suit the main flow):
    `name_field` / `email_field` / `interest_field` - journey_data keys to read;
    `interest` - a template over journey_data + text placeholders, e.g. "Booking: {book_detail}", used
    instead of `interest_field`; `thanks` - translation key of the confirmation message."""
    data = ctx.data
    name_field = node.get("name_field", "lead_name")
    email_field = node.get("email_field", "lead_email")
    interest_field = node.get("interest_field", "lead_interest")
    if "interest" in node:
        params = {k: v for k, v in data.items() if isinstance(v, str)}
        if ctx.niche:
            params.update(ctx.niche.params("en"))  # CRM records stay in English
        interest = node["interest"].format_map(_SafeDict(params))
    else:
        interest = data.get(interest_field)
    lead = LeadData(
        name=data.get(name_field, ""),
        email=data.get(email_field, "") if email_field else "",
        phone=ctx.user.wa_id,
        interest=interest,
    )
    crm_ref = ctx.services.crm.create_lead(ctx.db, lead)
    ctx.db.add(Lead(
        user_id=ctx.user.id, name=lead.name, email=lead.email, phone=lead.phone,
        interest=lead.interest, crm_ref=crm_ref, synced=crm_ref is not None,
    ))
    fields = [f for f in (name_field, email_field, interest_field, *node.get("clear", [])) if f]
    ctx.set_data(**dict.fromkeys(fields))
    thanks = ctx.t(node.get("thanks", "lead.thanks"), lead_name=lead.name, email=lead.email, **{
        k: v for k, v in data.items() if isinstance(v, str) and k not in ("lead_name", "email")
    })
    return ActionResult(messages=[TextOut(thanks)])


def send_otp(ctx: Context, node: dict) -> ActionResult:
    email = ctx.data.get("auth_email", "")
    customer = ctx.services.auth.start(ctx.db, ctx.user, email)
    if customer is None:
        return ActionResult(ok=False, messages=[TextOut(ctx.t("auth.not_found"))])
    return ActionResult(messages=[TextOut(ctx.t("auth.otp_sent", email_masked=mask_email(customer.email)))])


def verify_otp(ctx: Context, node: dict) -> ActionResult:
    code = ctx.data.get("auth_code", "")
    ctx.set_data(auth_code=None)
    result, left = ctx.services.auth.verify(ctx.db, ctx.user, code)
    if result is VerifyResult.OK:
        return ActionResult(messages=[TextOut(ctx.t("auth.success"))])
    if result is VerifyResult.INVALID:
        # re-ask silently: the error message already prompts for the code
        return ActionResult(ok=False, messages=[TextOut(ctx.t("auth.invalid_code", left=left))])
    key = "auth.expired" if result is VerifyResult.EXPIRED else "auth.too_many"
    return ActionResult(ok=False, messages=[TextOut(ctx.t(key))], goto=node.get("on_abort"))


def account_summary(ctx: Context, node: dict) -> ActionResult:
    customer = ctx.services.crm.get_customer(ctx.db, ctx.user.customer_ref or "")
    if customer is None:
        ctx.services.auth.logout(ctx.user)
        return ActionResult(ok=False, messages=[TextOut(ctx.t("auth.not_found"))])
    text = ctx.t(
        "account.summary",
        customer_name=customer.name, email=customer.email, plan=customer.plan, status=customer.status,
    )
    return ActionResult(messages=[TextOut(text)])


def logout(ctx: Context, node: dict) -> ActionResult:
    ctx.services.auth.logout(ctx.user)
    return ActionResult(messages=[TextOut(ctx.t("auth.logged_out"))])


def start_handoff(ctx: Context, node: dict) -> ActionResult:
    ctx.user.handoff = True
    ctx.services.crm.log_event("handoff.requested", {"wa_id": ctx.user.wa_id, "name": ctx.user.name})
    return ActionResult(messages=[TextOut(ctx.t("handoff.started"))])


ACTIONS = {
    "crm.create_lead": create_lead,
    "auth.send_otp": send_otp,
    "auth.verify_otp": verify_otp,
    "auth.logout": logout,
    "account.summary": account_summary,
    "handoff.start": start_handoff,
}
