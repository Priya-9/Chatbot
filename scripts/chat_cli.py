"""Chat with the bot in your terminal - no WhatsApp account needed. Great for demos and development.

    python scripts/chat_cli.py                 # uses LLM_PROVIDER (needs GROQ_API_KEY or ANTHROPIC_API_KEY)
    python scripts/chat_cli.py --offline       # no API key: AI replies show the retrieved RAG excerpts

Tap a button by typing its title or number (e.g. "1"). Type /quit to exit, /reset to start over.
OTP codes are printed in the log (no SMTP needed in development).
"""

import argparse
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.llm.claude import LLMResult  # noqa: E402
from app.main import bootstrap  # noqa: E402
from app.models import User  # noqa: E402
from app.services.container import build_services, set_services  # noqa: E402
from app.services.conversation import process_incoming  # noqa: E402
from app.whatsapp.client import ConsoleSender  # noqa: E402
from app.whatsapp.messages import ButtonsOut, Incoming, ListOut  # noqa: E402


class OfflineLLM:
    """Stands in for Claude: echoes the retrieved knowledge so you can see RAG working without a key."""

    def complete(self, system: str, messages: list[dict]) -> LLMResult:
        turn = messages[-1]["content"]
        kb = turn.split("<knowledge_base>")[1].split("</knowledge_base>")[0].strip()
        return LLMResult(text="[offline mode — top retrieved excerpt]\n" + kb[:700])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="don't call the LLM")
    parser.add_argument("--phone", default="15550001111", help="simulated WhatsApp number")
    parser.add_argument("--name", default="Alex")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252, which can't print emoji
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING, format="  [log] %(message)s")
    set_services(build_services(llm=OfflineLLM() if args.offline else None))
    bootstrap()

    sender = ConsoleSender()
    last_options: list[tuple[str, str]] = []
    print(__doc__)

    def send(text: str, reply_id: str | None = None) -> None:
        nonlocal last_options
        inc = Incoming(wa_id=args.phone, message_id=f"cli-{uuid.uuid4()}", type="interactive" if reply_id else "text",
                       text=text, reply_id=reply_id, name=args.name)
        replies = process_incoming(inc, sender)
        last_options = []
        for reply in replies:
            if isinstance(reply, ButtonsOut):
                last_options = reply.buttons
            elif isinstance(reply, ListOut):
                last_options = [(rid, title) for rid, title, _ in reply.rows]
        if any(isinstance(r, (ButtonsOut, ListOut)) for r in replies):
            print("  " + "  ".join(f"({i}) {t}" for i, (_, t) in enumerate(last_options, 1)))

    send("hi")
    while True:
        try:
            text = input("\n👤 you: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text == "/quit":
            break
        if text == "/reset":
            with session_scope() as db:
                user = db.scalar(select(User).where(User.wa_id == args.phone))
                if user:
                    db.delete(user)
            last_options = []
            send("hi")
            continue
        # map a number or a title to a button tap, like WhatsApp would
        option = None
        if text.isdigit() and 1 <= int(text) <= len(last_options):
            option = last_options[int(text) - 1]
        else:
            option = next((o for o in last_options if o[1].lower() == text.lower()), None)
        if option:
            send(option[1], reply_id=option[0])
        elif text:
            send(text)


if __name__ == "__main__":
    main()
