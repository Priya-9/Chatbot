"""RAG answer generation: retrieve knowledge, add conversation memory, ask the LLM."""

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.demo.niches import Niche
from app.i18n.translator import Translator
from app.llm.claude import LLM, LLMError
from app.models import Message, User
from app.rag.retriever import Retriever

log = logging.getLogger(__name__)

# Fallback when SYSTEM_PROMPT_FILE is missing. Each client deployment mounts its own prompt file.
DEFAULT_SYSTEM_PROMPT = """\
You are the WhatsApp assistant for {business}. Answer only from the knowledge-base excerpts provided with \
each message; if they don't cover the question, say so and suggest typing *human*. Keep replies short and \
use WhatsApp formatting only. Reply in the language named in the message. Never ask for passwords, card \
numbers or one-time codes."""


def load_system_prompt(settings: Settings) -> str:
    """Read the client's prompt file. It is loaded once and kept static, so the prefix stays byte-identical
    and cacheable; anything that varies per request (context, language) goes in the user turn."""
    path = Path(settings.system_prompt_file)
    if path.is_file():
        template = path.read_text(encoding="utf-8").strip()
    else:
        log.warning("System prompt file %s not found - using the built-in default", path)
        template = DEFAULT_SYSTEM_PROMPT
    # str.replace rather than str.format, so braces in a client's prompt need no escaping.
    return template.replace("{business}", settings.business_name)


class AIAssistant:
    def __init__(self, llm: LLM, retriever: Retriever, translator: Translator, settings: Settings,
                 niches: dict[str, Niche] | None = None):
        self.llm = llm
        self.niches = niches or {}
        self.retriever = retriever
        self.translator = translator
        self.settings = settings
        self.system_prompt = load_system_prompt(settings)

    def _history(self, db: Session, user: User, exclude_id: int | None) -> list[dict]:
        limit = self.settings.llm_history_turns * 2
        stmt = select(Message).where(Message.user_id == user.id, Message.ai.is_(True))
        if exclude_id is not None:
            stmt = stmt.where(Message.id != exclude_id)
        niche_from = (user.journey_data or {}).get("niche_from")
        if niche_from:  # demo mode: forget the chat about the previous sample business
            stmt = stmt.where(Message.id > niche_from)
        rows = list(db.scalars(stmt.order_by(Message.id.desc()).limit(limit)))[::-1]
        history = [
            {"role": "user" if m.direction == "in" else "assistant", "content": m.content} for m in rows
        ]
        while history and history[0]["role"] != "user":  # conversation must start with a user turn
            history.pop(0)
        return history

    def build_user_turn(self, question: str, language: str, niche: Niche | None = None) -> str:
        hits = self.retriever.search(question, self.settings.rag_top_k, scope=niche.knowledge if niche else None)
        if hits:
            excerpts = "\n\n".join(
                f'<excerpt source="{h.source}">\n{h.text}\n</excerpt>' for h in hits
            )
        else:
            excerpts = "(no relevant excerpts found)"
        # per-request, so it belongs in the user turn: the system prompt stays byte-identical for caching
        business = ""
        if niche:
            business = f"Business you represent: {niche.text('business', 'en')} ({niche.text('title', 'en')})\n\n"
        return (
            f"{business}<knowledge_base>\n{excerpts}\n</knowledge_base>\n\n"
            f"Reply language: {self.translator.english_name(language)}\n\n"
            f"Customer message:\n{question}"
        )

    def answer(self, db: Session, user: User, question: str, exclude_message_id: int | None = None) -> str:
        language = self.translator.resolve(user.language)
        messages = self._history(db, user, exclude_message_id)
        niche = self.niches.get((user.journey_data or {}).get("niche") or "")
        messages.append({"role": "user", "content": self.build_user_turn(question, language, niche)})
        try:
            result = self.llm.complete(self.system_prompt, messages)
        except LLMError:
            return self.translator.t("ai.unavailable", language)
        if result.refused or not result.text:
            return self.translator.t("ai.refusal", language)
        return result.text
