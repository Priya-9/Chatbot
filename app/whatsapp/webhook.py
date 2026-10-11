"""Webhook endpoints Meta calls: GET for verification, POST for inbound messages."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.config import get_settings
from app.services.conversation import process_incoming
from app.whatsapp.messages import Incoming

log = logging.getLogger(__name__)
router = APIRouter(tags=["whatsapp"])


def verify_signature(app_secret: str, body: bytes, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


def parse_webhook(payload: dict) -> list[Incoming]:
    """Extract user messages from a WhatsApp webhook payload (status updates are ignored)."""
    result: list[Incoming] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}
            for msg in value.get("messages", []):
                mtype = msg.get("type", "")
                text, reply_id = "", None
                if mtype == "text":
                    text = msg.get("text", {}).get("body", "")
                elif mtype == "interactive":
                    inter = msg.get("interactive", {})
                    reply = inter.get("button_reply") or inter.get("list_reply") or {}
                    reply_id, text = reply.get("id"), reply.get("title", "")
                elif mtype == "button":  # quick-reply button on a template message
                    reply_id = msg.get("button", {}).get("payload")
                    text = msg.get("button", {}).get("text", "")
                result.append(Incoming(
                    wa_id=msg.get("from", ""),
                    message_id=msg.get("id", ""),
                    type=mtype,
                    text=text,
                    reply_id=reply_id,
                    name=names.get(msg.get("from")),
                ))
    return result


@router.get("/webhook", response_class=PlainTextResponse)
def verify_webhook(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
):
    settings = get_settings()
    if mode == "subscribe" and hmac.compare_digest(token, settings.whatsapp_verify_token):
        return challenge
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    settings = get_settings()
    body = await request.body()

    if settings.whatsapp_app_secret:
        if not verify_signature(settings.whatsapp_app_secret, body, request.headers.get("X-Hub-Signature-256")):
            raise HTTPException(status_code=401, detail="Invalid signature")
    elif settings.is_production:
        raise HTTPException(status_code=500, detail="WHATSAPP_APP_SECRET must be set in production")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Acknowledge immediately; Meta retries if we take too long. Processing happens in the background.
    sender = request.app.state.sender
    for incoming in parse_webhook(payload):
        background_tasks.add_task(process_incoming, incoming, sender)
    return {"status": "ok"}
