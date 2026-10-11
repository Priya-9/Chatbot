"""Checks the exact HTTP request ClaudeLLM sends, using a mock transport (no network, no API key)."""

import json

import httpx2
import pytest
from anthropic import DefaultHttpxClient

from app.config import Settings
from app.llm.claude import ClaudeLLM, LLMError


def make_llm(handler, **overrides) -> ClaudeLLM:
    llm = ClaudeLLM(Settings(anthropic_api_key="test-key", **overrides))
    llm.client = llm.client.with_options(
        http_client=DefaultHttpxClient(transport=httpx2.MockTransport(handler)), max_retries=0
    )
    return llm


def message_response(content, stop_reason="end_turn"):
    return {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": content, "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def test_request_shape_with_fallbacks_and_caching():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta")
        return httpx2.Response(200, json=message_response([
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": "Hello!"},
        ]))

    result = make_llm(handler).complete("SYSTEM", [{"role": "user", "content": "hi"}])

    assert result.text == "Hello!" and not result.refused
    body = seen["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert seen["beta"] == "server-side-fallback-2026-07-01"
    assert body["system"] == [{"type": "text", "text": "SYSTEM", "cache_control": {"type": "ephemeral"}}]
    assert body["output_config"] == {"effort": "low"}
    assert "thinking" not in body  # Opus 5.5 thinks adaptively by default; disabling it is a 400


def test_fallbacks_can_be_disabled_for_other_platforms():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta")
        return httpx2.Response(200, json=message_response([{"type": "text", "text": "ok"}]))

    make_llm(handler, llm_fallbacks=False).complete("S", [{"role": "user", "content": "hi"}])
    assert "fallbacks" not in seen["body"] and seen["beta"] is None


def test_refusal_is_reported():
    handler = lambda request: httpx2.Response(200, json=message_response([], stop_reason="refusal"))  # noqa: E731
    assert make_llm(handler).complete("S", [{"role": "user", "content": "x"}]).refused


def test_api_errors_become_llm_error():
    def handler(request):
        return httpx2.Response(529, json={"type": "error", "error": {"type": "overloaded_error", "message": "busy"}})

    with pytest.raises(LLMError):
        make_llm(handler).complete("S", [{"role": "user", "content": "x"}])
