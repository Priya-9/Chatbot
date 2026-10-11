from sqlalchemy import select

from app.db import session_scope
from app.models import Lead, Message, User
from app.whatsapp.messages import ButtonsOut, ListOut, TextOut


def texts(replies):
    return [r.body for r in replies]


def user(wa_id="15550001111") -> User:
    with session_scope() as db:
        return db.scalar(select(User).where(User.wa_id == wa_id))


def start_in_english(chat):
    chat("hi")
    return chat("English", reply_id="lang:en")


def test_first_contact_asks_for_language(chat):
    replies = chat("hello there")
    assert len(replies) == 1
    assert isinstance(replies[0], ListOut)
    assert ("lang:es", "Español", "Spanish") in replies[0].rows


def test_language_selection_shows_welcome_and_menu(chat):
    replies = start_in_english(chat)
    assert "Language set to English" in replies[0].body
    assert "Welcome to *Acme Cloud*" in replies[1].body
    menu = replies[2]
    assert isinstance(menu, ListOut)
    assert [row[0] for row in menu.rows] == ["ask_ai", "book_demo", "account", "human", "language"]
    assert user().language == "en"


def test_language_by_typed_name_and_translated_menu(chat):
    chat("hi")
    replies = chat("español")
    assert "español" in replies[0].body
    assert replies[2].rows[0][1] == "Hacer una pregunta"


def test_returning_user_skips_language(chat):
    start_in_english(chat)
    replies = chat("menu")
    assert isinstance(replies[0], ListOut)


def test_invalid_menu_choice_without_text_reprompts(chat):
    start_in_english(chat)
    replies = chat("", reply_id="nonexistent")
    assert "didn't catch that" in replies[0].body
    assert isinstance(replies[1], ListOut)


def test_menu_option_by_number(chat):
    start_in_english(chat)
    replies = chat("2")
    assert "full name" in replies[0].body


def test_lead_capture_saves_lead(chat):
    start_in_english(chat)
    assert "full name" in chat("", reply_id="book_demo")[0].body
    assert "email" in chat("Alex Smith")[0].body
    assert "valid email" in chat("not-an-email")[0].body
    assert "demo" in chat("alex@company.com")[0].body
    replies = chat("Automations and client portals")
    assert "Alex Smith" in replies[0].body and "alex@company.com" in replies[0].body
    assert isinstance(replies[1], ListOut)  # back to the menu

    with session_scope() as db:
        lead = db.scalar(select(Lead))
        assert (lead.name, lead.email, lead.phone) == ("Alex Smith", "alex@company.com", "15550001111")
        assert lead.interest == "Automations and client portals"
    assert user().journey_data.get("lead_name") is None  # temp data cleared


def test_ai_mode_uses_rag_context_and_memory(chat, llm):
    start_in_english(chat)
    assert "Ask me anything" in chat("", reply_id="ask_ai")[0].body

    replies = chat("What is the refund policy for annual plans?")
    assert replies == [TextOut("FAKE ANSWER", ai=True)]
    system, messages = llm.calls[-1]
    assert "Acme Cloud" in system
    assert "refunded in full within 30 days" in messages[-1]["content"]
    assert "Reply language: English" in messages[-1]["content"]

    llm.reply = "SECOND"
    chat("And for monthly plans?")
    _, messages = llm.calls[-1]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert messages[0]["content"] == "What is the refund policy for annual plans?"
    assert messages[1]["content"] == "FAKE ANSWER"


def test_free_text_at_menu_goes_to_ai(chat, llm):
    start_in_english(chat)
    replies = chat("How much is the Pro plan?")
    assert replies[0].body == "FAKE ANSWER"
    assert user().journey_node == "ai_chat"
    assert "$12 per user" in llm.calls[-1][1][-1]["content"]


def test_ai_answers_in_users_language(chat, llm):
    chat("hi")
    chat("हिन्दी", reply_id="lang:hi")
    chat("प्रो प्लान की कीमत क्या है?")
    assert "Reply language: Hindi" in llm.calls[-1][1][-1]["content"]


def test_ai_refusal_is_friendly(chat, llm):
    start_in_english(chat)
    llm.refuse = True
    replies = chat("something the model declines")
    assert "not able to help" in replies[0].body


def test_account_requires_otp_then_returns(chat, otp_box):
    start_in_english(chat)
    replies = chat("", reply_id="account")
    assert "registered with us" in replies[0].body

    assert "couldn't find an account" in chat("nobody@example.com")[0].body
    chat("", reply_id="account")
    replies = chat("jane@example.com")
    assert "ja••@example.com" in replies[0].body
    code = otp_box["jane@example.com"]

    wrong = "000000" if code != "000000" else "111111"
    assert "Attempts left: 4" in chat(wrong)[0].body
    assert "6-digit code" in chat("12")[0].body  # format validation

    replies = chat(code)
    assert texts(replies)[0] == "Verified ✅"
    assert "Name: Jane Doe" in replies[1].body and "Plan: Pro" in replies[1].body
    assert isinstance(replies[2], ListOut)

    # session persists: no second OTP
    replies = chat("", reply_id="account")
    assert "Name: Jane Doe" in replies[0].body

    chat("logout")
    assert "registered with us" in chat("", reply_id="account")[0].body


def test_otp_lockout_after_max_attempts(chat, otp_box):
    start_in_english(chat)
    chat("", reply_id="account")
    chat("jane@example.com")
    wrong = "000000" if otp_box["jane@example.com"] != "000000" else "111111"
    for _ in range(4):
        chat(wrong)
    replies = chat(wrong)
    assert "Too many incorrect attempts" in replies[0].body
    assert isinstance(replies[1], ListOut)
    assert user().customer_ref is None


def test_handoff_silences_bot_until_resumed(chat, sender):
    start_in_english(chat)
    assert "human agent" in chat("human")[0].body
    assert user().handoff is True
    assert chat("Hello? I need help with billing") == []

    replies = chat("bot")
    assert "back with the virtual assistant" in replies[0].body
    assert isinstance(replies[1], ListOut)
    assert user().handoff is False


def test_non_text_message(chat):
    start_in_english(chat)
    replies = chat("", mtype="image")
    assert "only read text" in replies[0].body


def test_messages_are_logged_and_marked_read(chat, sender):
    start_in_english(chat)
    with session_scope() as db:
        rows = db.scalars(select(Message).order_by(Message.id)).all()
        assert [m.direction for m in rows][:2] == ["in", "out"]
    assert len(sender.read) == 2
    assert all(to == "15550001111" for to, _ in sender.sent)


def test_three_or_fewer_options_render_as_buttons(services):
    from app.journeys.engine import Context, JourneyEngine
    from app.models import User as U

    flow = {
        "start": "m",
        "nodes": {
            "m": {"type": "menu", "text": "menu.prompt",
                  "options": [{"id": "a", "label": "menu.ask_ai", "next": "m"}]},
        },
    }
    engine = JourneyEngine(flow, {})
    out = []
    engine.goto(Context(db=None, user=U(wa_id="1", journey_data={}), services=services), "m", out)
    assert isinstance(out[0], ButtonsOut) and out[0].buttons == [("a", "Ask a question")]


def test_flow_validation_catches_bad_references():
    import pytest

    from app.journeys.engine import JourneyEngine

    with pytest.raises(ValueError, match="undefined nodes"):
        JourneyEngine({"start": "a", "nodes": {"a": {"type": "message", "text": "x", "next": "missing"}}}, {})
