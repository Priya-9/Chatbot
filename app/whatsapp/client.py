"""WhatsApp Business Cloud API client (Meta Graph API) plus a console sender for local development."""

import logging
import sys
from typing import Protocol

import httpx

from app.config import Settings
from app.whatsapp.messages import ButtonsOut, ListOut, Outgoing, TextOut, outgoing_as_text

log = logging.getLogger(__name__)

MAX_TEXT_LEN = 4096
MAX_BUTTON_TITLE = 20
MAX_ROW_TITLE = 24
MAX_ROW_DESCRIPTION = 72
MAX_INTERACTIVE_BODY = 1024


class Sender(Protocol):
    def send(self, to: str, message: Outgoing) -> None: ...

    def mark_read(self, message_id: str) -> None: ...


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def split_text(text: str, limit: int = MAX_TEXT_LEN) -> list[str]:
    """Split long replies on paragraph/line boundaries to respect WhatsApp's 4096-char limit."""
    if len(text) <= limit:
        return [text]
    parts, current = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:  # a single enormous line
            parts.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            parts.append(current)
            current = ""
        current += line
    if current.strip():
        parts.append(current)
    return [p.strip() for p in parts if p.strip()]


def build_payloads(to: str, message: Outgoing) -> list[dict]:
    base = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to}
    if isinstance(message, TextOut):
        return [
            {**base, "type": "text", "text": {"body": chunk, "preview_url": False}}
            for chunk in split_text(message.body)
        ]
    if isinstance(message, ButtonsOut):
        buttons = [
            {"type": "reply", "reply": {"id": bid, "title": _clip(title, MAX_BUTTON_TITLE)}}
            for bid, title in message.buttons[:3]
        ]
        return [{
            **base,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": _clip(message.body, MAX_INTERACTIVE_BODY)},
                "action": {"buttons": buttons},
            },
        }]
    if isinstance(message, ListOut):
        rows = []
        for rid, title, desc in message.rows[:10]:
            row = {"id": rid, "title": _clip(title, MAX_ROW_TITLE)}
            if desc:
                row["description"] = _clip(desc, MAX_ROW_DESCRIPTION)
            rows.append(row)
        section = {"rows": rows}
        if message.section_title:
            section["title"] = _clip(message.section_title, MAX_ROW_TITLE)
        return [{
            **base,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": _clip(message.body, MAX_INTERACTIVE_BODY)},
                "action": {"button": _clip(message.button, MAX_BUTTON_TITLE), "sections": [section]},
            },
        }]
    raise TypeError(f"Unsupported message type: {type(message)!r}")


class WhatsAppClient:
    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.settings = settings
        self.url = (
            f"{settings.whatsapp_api_base}/{settings.whatsapp_api_version}"
            f"/{settings.whatsapp_phone_number_id}/messages"
        )
        self.http = http or httpx.Client(
            timeout=15.0, headers={"Authorization": f"Bearer {settings.whatsapp_token}"}
        )

    def _post(self, payload: dict) -> dict | None:
        try:
            resp = self.http.post(self.url, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            log.error("WhatsApp API error %s: %s", exc.response.status_code, exc.response.text)
        except httpx.HTTPError as exc:
            log.error("WhatsApp API request failed: %s", exc)
        return None

    def send(self, to: str, message: Outgoing) -> None:
        for payload in build_payloads(to, message):
            self._post(payload)

    def mark_read(self, message_id: str) -> None:
        self._post({"messaging_product": "whatsapp", "status": "read", "message_id": message_id})


class ConsoleSender:
    """Prints messages instead of calling Meta. Used by the CLI simulator and when no token is configured."""

    def __init__(self):
        self.sent: list[tuple[str, Outgoing]] = []

    def send(self, to: str, message: Outgoing) -> None:
        self.sent.append((to, message))
        text = f"\n🤖 → {to}:\n{outgoing_as_text(message)}"
        try:
            print(text, flush=True)
        except UnicodeEncodeError:  # e.g. a cp1252 Windows console: drop what it can't display
            encoding = getattr(sys.stdout, "encoding", None) or "ascii"
            print(text.encode(encoding, "replace").decode(encoding), flush=True)

    def mark_read(self, message_id: str) -> None:
        pass
