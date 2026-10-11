import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.whatsapp.client import build_payloads, split_text
from app.whatsapp.messages import ButtonsOut, ListOut, TextOut
from app.whatsapp.webhook import parse_webhook

SECRET = b"test-app-secret"


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()


def text_payload(text="hi", wa_id="15550002222", msg_id="wamid.ABC"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp",
            "contacts": [{"wa_id": wa_id, "profile": {"name": "Sam"}}],
            "messages": [{"from": wa_id, "id": msg_id, "type": "text", "text": {"body": text}}],
        }}]}],
    }


@pytest.fixture
def client(services, sender):
    with TestClient(app) as c:
        app.state.sender = sender
        yield c


def test_webhook_verification(client):
    ok = client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "test-verify-token",
                                        "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.text == "12345"
    bad = client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"})
    assert bad.status_code == 403


def test_webhook_rejects_bad_signature(client):
    body = json.dumps(text_payload()).encode()
    assert client.post("/webhook", content=body, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 401
    assert client.post("/webhook", content=body).status_code == 401


def test_webhook_processes_message_and_dedupes(client, sender):
    body = json.dumps(text_payload()).encode()
    headers = {"X-Hub-Signature-256": sign(body), "Content-Type": "application/json"}
    assert client.post("/webhook", content=body, headers=headers).json() == {"status": "ok"}
    assert len(sender.sent) == 1 and isinstance(sender.sent[0][1], ListOut)

    client.post("/webhook", content=body, headers=headers)  # Meta retry with the same message id
    assert len(sender.sent) == 1


def test_parse_interactive_and_status_payloads():
    payload = {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "1", "profile": {"name": "A"}}],
        "messages": [{"from": "1", "id": "m1", "type": "interactive",
                      "interactive": {"type": "list_reply", "list_reply": {"id": "ask_ai", "title": "Ask"}}}],
        "statuses": [{"id": "x", "status": "delivered"}],
    }}]}]}
    [inc] = parse_webhook(payload)
    assert (inc.reply_id, inc.text, inc.name) == ("ask_ai", "Ask", "A")
    assert parse_webhook({"entry": [{"changes": [{"value": {"statuses": [{}]}}]}]}) == []


def test_payload_builders_respect_whatsapp_limits():
    [btn] = build_payloads("1", ButtonsOut("Body", [("a", "A very long button title here")]))
    assert len(btn["interactive"]["action"]["buttons"][0]["reply"]["title"]) <= 20
    [lst] = build_payloads("1", ListOut("Body", "Options", [(str(i), f"Row {i}", "") for i in range(15)]))
    assert len(lst["interactive"]["action"]["sections"][0]["rows"]) == 10
    long_text = "\n".join(["x" * 100] * 100)
    assert all(len(p) <= 4096 for p in split_text(long_text))
    assert len(build_payloads("1", TextOut(long_text))) == 3


def test_admin_requires_auth_and_lists_data(client, chat):
    assert client.get("/admin/stats").status_code == 401
    assert client.post("/admin/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    token = client.post("/admin/login", json={"username": "admin", "password": "secret-pass"}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    chat("hi")
    stats = client.get("/admin/stats", headers=h).json()
    assert stats["users"] == 1 and stats["customers"] == 2 and stats["knowledge_chunks"] > 0

    users = client.get("/admin/users", headers=h).json()
    uid = users[0]["id"]
    msgs = client.get(f"/admin/users/{uid}/messages", headers=h).json()
    assert msgs[0]["direction"] == "in"

    assert client.post(f"/admin/users/{uid}/reply", json={"text": "Hi from an agent"}, headers=h).status_code == 200
    created = client.post("/admin/customers", json={"email": "new@example.com", "name": "New"}, headers=h)
    assert created.status_code == 201
    assert client.post("/admin/customers", json={"email": "new@example.com", "name": "New"}, headers=h).status_code == 409
    assert client.get("/admin/knowledge", headers=h).json()
