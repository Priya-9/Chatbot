"""Handles one inbound WhatsApp message end-to-end: dedupe, user lookup, journey, reply, logging."""

import logging
import threading
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import session_scope
from app.journeys.engine import Context
from app.models import Message, User, utcnow
from app.services.container import get_services
from app.whatsapp.client import Sender
from app.whatsapp.messages import Incoming, Outgoing, TextOut, outgoing_as_text

log = logging.getLogger(__name__)

# Serialise messages from the same user so rapid-fire messages can't race on journey state.
# (Per-process; with multiple workers, route users consistently or use a distributed lock.)
_user_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)


def get_or_create_user(db, wa_id: str, name: str | None) -> User:
    user = db.scalar(select(User).where(User.wa_id == wa_id))
    if user is None:
        user = User(wa_id=wa_id, name=name, journey_data={})
        db.add(user)
        db.flush()
    elif name and user.name != name:
        user.name = name
    user.last_seen_at = utcnow()
    return user


def _describe_inbound(inc: Incoming) -> str:
    return inc.text if inc.text else f"[{inc.type}]"


def process_incoming(inc: Incoming, sender: Sender) -> list[Outgoing]:
    services = get_services()
    replies: list[Outgoing] = []

    with _user_locks[inc.wa_id]:
        try:
            with session_scope() as db:
                user = get_or_create_user(db, inc.wa_id, inc.name)
                inbound = Message(
                    user_id=user.id, direction="in", sender="user",
                    content=_describe_inbound(inc), wa_message_id=inc.message_id or None,
                )
                db.add(inbound)
                try:
                    db.flush()
                except IntegrityError:
                    log.info("Duplicate webhook delivery for %s ignored", inc.message_id)
                    db.rollback()
                    return []

                ctx = Context(db=db, user=user, services=services, inbound=inbound)
                text = (inc.text or "").strip().lower()

                if user.handoff:
                    if text in {k.lower() for k in services.engine.flow.get("resume_keywords", [])}:
                        user.handoff = False
                        replies.append(TextOut(ctx.t("handoff.ended")))
                        services.engine.goto(ctx, services.engine.home, replies)
                    # otherwise a human agent is handling this chat: stay silent
                elif inc.type not in ("text", "interactive", "button"):
                    replies.append(TextOut(ctx.t("common.text_only")))
                else:
                    replies = services.engine.handle(ctx, inc)

                for reply in replies:
                    db.add(Message(
                        user_id=user.id, direction="out", sender="bot",
                        content=outgoing_as_text(reply), ai=getattr(reply, "ai", False),
                    ))
        except Exception:
            log.exception("Failed to process message %s from %s", inc.message_id, inc.wa_id)
            fallback = services.translator.t("common.error")
            sender.send(inc.wa_id, TextOut(fallback))
            return [TextOut(fallback)]

    # send after commit, so state is saved even if Meta is slow
    if inc.message_id:
        sender.mark_read(inc.message_id)
    for reply in replies:
        sender.send(inc.wa_id, reply)
    return replies
