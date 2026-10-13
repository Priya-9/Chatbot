"""Sales-demo mode: niche selection, niche-scoped RAG, booking and prospect leads."""

import uuid

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db import Base, get_engine, session_scope
from app.demo.niches import load_niches
from app.models import Lead, User
from app.rag.ingest import ingest_directory
from app.services.container import build_services, set_services
from app.services.conversation import process_incoming
from app.whatsapp.messages import Incoming, ListOut


@pytest.fixture
def demo(llm, sender):
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    settings = get_settings().model_copy(update={
        "business_name": "Priya AI Bots",
        "niches_file": "demo/niches.yaml",
        "knowledge_dir": "demo/knowledge",
        "journey_file": "app/journeys/flows/demo.yaml",
        "system_prompt_file": "demo/system_prompt.md",
    })
    svc = build_services(settings, llm=llm)
    set_services(svc)
    with session_scope() as db:
        ingest_directory(db, svc.retriever, settings.knowledge_dir)

    def _chat(text: str = "", reply_id: str | None = None):
        inc = Incoming(wa_id="15550002222", message_id=f"wamid.{uuid.uuid4()}",
                       type="interactive" if reply_id else "text", text=text, reply_id=reply_id, name="Alex")
        return process_incoming(inc, sender)

    yield _chat
    set_services(None)


def bodies(replies):
    return "\n".join(r.body for r in replies)


def start(chat, niche="niche:clinic"):
    chat("hi")
    chat("English", reply_id="lang:en")
    return chat("", reply_id=niche)


def test_every_niche_is_valid_and_has_knowledge():
    from pathlib import Path

    niches = load_niches("demo/niches.yaml")
    assert 1 <= len(niches) <= 10
    for niche in niches.values():
        assert len(niche.text("title", "en")) <= 24, niche.id
        assert len(niche.text("description", "en")) <= 72, niche.id
        assert len(niche.text("booking.label", "en")) <= 24, niche.id
        assert niche.text("booking.ask_detail", "en") and niche.text("booking.ask_when", "en"), niche.id
        assert list(Path("demo/knowledge", niche.knowledge).glob("*.md")), niche.id


def test_first_question_after_language_is_the_niche(demo):
    demo("hi")
    replies = demo("English", reply_id="lang:en")
    niche_list = replies[-1]
    assert isinstance(niche_list, ListOut)
    assert "Priya AI Bots" in niche_list.body
    assert niche_list.rows[0][0] == "niche:clinic"


def test_choosing_niche_role_plays_that_business(demo):
    replies = start(demo)
    assert "SmileCare Dental & Skin Clinic" in bodies(replies)
    assert "root canal" in bodies(replies)  # example questions shown
    menu = replies[-1]
    assert [row[0] for row in menu.rows] == ["ask_ai", "book", "human", "get_bot", "switch"]
    assert menu.rows[1][1] == "Book appointment"


def test_niche_can_be_typed_in_free_text(demo):
    demo("hi")
    demo("English", reply_id="lang:en")
    replies = demo("I run a small gym in Pune")
    assert "IronFit" in bodies(replies)


def test_ai_is_scoped_to_the_chosen_niche(demo, llm):
    start(demo, "niche:salon")
    demo("what is the price of keratin and root canal?")
    turn = llm.calls[-1][1][-1]["content"]
    assert "Business you represent: Glow Studio Unisex Salon" in turn
    assert 'source="salon/' in turn
    assert 'source="clinic/' not in turn


def test_switching_niche_resets_ai_memory(demo, llm):
    start(demo, "niche:salon")
    demo("keratin price?")
    demo("switch")
    demo("", reply_id="niche:restaurant")
    demo("do you have jain food?")
    history = llm.calls[-1][1]
    assert len(history) == 1  # no salon chat carried over
    assert "The Spice Route Kitchen" in history[0]["content"]


def test_demo_booking_is_saved_as_lead(demo):
    start(demo, "niche:restaurant")
    demo("", reply_id="book")
    demo("Alex Smith")
    demo("4 people, birthday")
    replies = demo("Friday 8:30 pm")
    assert "Thank you Alex Smith" in bodies(replies)
    assert "Behind the scenes" in bodies(replies)
    with session_scope() as db:
        lead = db.scalar(select(Lead))
        assert lead.name == "Alex Smith"
        assert lead.interest == (
            "[DEMO BOOKING] Restaurant / Cafe / The Spice Route Kitchen: 4 people, birthday, when: Friday 8:30 pm"
        )


def test_booking_question_uses_niche_wording(demo):
    start(demo, "niche:restaurant")
    demo("", reply_id="book")
    replies = demo("Alex")
    assert "How many guests" in bodies(replies)


def test_get_bot_captures_prospect(demo):
    start(demo, "niche:hotel")
    replies = demo("", reply_id="get_bot")
    assert "Priya AI Bots" in bodies(replies)
    demo("Rahul")
    replies = demo("Hilltop Resort, Shimla")
    assert "Hilltop Resort, Shimla" in bodies(replies)
    with session_scope() as db:
        lead = db.scalar(select(Lead))
        assert (lead.name, lead.phone) == ("Rahul", "15550002222")
        assert lead.interest == "[PROSPECT] Hilltop Resort, Shimla (tried the Hotel / Homestay demo)"
        user = db.scalar(select(User))
        assert user.journey_data.get("prospect_company") is None


def test_hindi_user_gets_hindi_niche_labels(demo):
    demo("hi")
    replies = demo("हिन्दी", reply_id="lang:hi")
    assert replies[-1].rows[0][1] == "क्लिनिक / डेंटल"
