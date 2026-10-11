import os
import tempfile
import uuid
from pathlib import Path

# Configure the app for tests *before* anything imports settings.
_tmp = Path(tempfile.mkdtemp(prefix="wa-bot-tests-"))
os.environ.update({
    "DATABASE_URL": f"sqlite:///{(_tmp / 'test.db').as_posix()}",
    "ENVIRONMENT": "development",
    "WHATSAPP_APP_SECRET": "test-app-secret",
    "WHATSAPP_VERIFY_TOKEN": "test-verify-token",
    "WHATSAPP_TOKEN": "",
    "CRM_PROVIDER": "local",
    "RAG_BACKEND": "bm25",
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": "secret-pass",
    "JWT_SECRET": "test-jwt-secret-that-is-long-enough-for-hs256",
    "ANTHROPIC_API_KEY": "test-key",
})

import pytest  # noqa: E402

from app.db import Base, get_engine, session_scope  # noqa: E402
from app.llm.claude import LLMResult  # noqa: E402
from app.main import DEMO_CUSTOMERS  # noqa: E402
from app.models import Customer  # noqa: E402
from app.rag.ingest import ingest_directory  # noqa: E402
from app.services.container import build_services, set_services  # noqa: E402
from app.services.conversation import process_incoming  # noqa: E402
from app.whatsapp.messages import Incoming  # noqa: E402


class FakeLLM:
    def __init__(self):
        self.calls: list[tuple[str, list[dict]]] = []
        self.reply = "FAKE ANSWER"
        self.refuse = False

    def complete(self, system: str, messages: list[dict]) -> LLMResult:
        self.calls.append((system, messages))
        return LLMResult(text="" if self.refuse else self.reply, refused=self.refuse)


class RecordingSender:
    def __init__(self):
        self.sent = []
        self.read = []

    def send(self, to, message):
        self.sent.append((to, message))

    def mark_read(self, message_id):
        self.read.append(message_id)


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def otp_box():
    """Captures OTP codes instead of emailing them: {email: code}."""
    return {}


@pytest.fixture
def services(llm, otp_box):
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    svc = build_services(llm=llm, otp_delivery=lambda email, code: otp_box.__setitem__(email, code))
    set_services(svc)
    with session_scope() as db:
        db.add_all(Customer(**c) for c in DEMO_CUSTOMERS)
        ingest_directory(db, svc.retriever, "knowledge")
    yield svc
    set_services(None)


@pytest.fixture
def sender():
    return RecordingSender()


@pytest.fixture
def chat(services, sender):
    """chat("text") or chat(reply_id="ask_ai") -> list of replies for that turn."""

    def _chat(text: str = "", reply_id: str | None = None, wa_id: str = "15550001111", mtype: str | None = None):
        inc = Incoming(
            wa_id=wa_id, message_id=f"wamid.{uuid.uuid4()}",
            type=mtype or ("interactive" if reply_id else "text"),
            text=text, reply_id=reply_id, name="Alex",
        )
        return process_incoming(inc, sender)

    return _chat
