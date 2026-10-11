"""Checks the exact HTTP request GroqLLM sends, using a mock transport (no network, no API key)."""

import json

import httpx
import pytest

from app.config import Settings
from app.llm.claude import LLMError
from app.llm.groq import GroqLLM
from app.services.container import build_llm


def make_llm(handler, **overrides) -> GroqLLM:
    llm = GroqLLM(Settings(groq_api_key="test-key", **overrides), max_retries=0)
    llm.client = httpx.Client(
        base_url=llm.settings.groq_api_base, headers=llm.client.headers, transport=httpx.MockTransport(handler)
    )
    return llm


def completion(content, finish_reason="stop"):
    return {
        "id": "chatcmpl-1", "object": "chat.completion", "model": "openai/gpt-oss-120b",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


def test_request_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=completion("Hello!"))

    result = make_llm(handler).complete("SYSTEM", [{"role": "user", "content": "hi"}])

    assert result.text == "Hello!" and not result.refused
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["auth"] == "Bearer test-key"
    body = seen["body"]
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["messages"] == [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "hi"}]
    assert body["reasoning_effort"] == "low"
    assert body["max_completion_tokens"] == 4096


def test_content_filter_is_reported_as_refusal():
    handler = lambda request: httpx.Response(200, json=completion(None, "content_filter"))  # noqa: E731
    assert make_llm(handler).complete("S", [{"role": "user", "content": "x"}]).refused


@pytest.mark.parametrize("status", [401, 429, 503])
def test_api_errors_become_llm_error(status):
    handler = lambda request: httpx.Response(status, json={"error": {"message": "nope"}})  # noqa: E731
    with pytest.raises(LLMError):
        make_llm(handler).complete("S", [{"role": "user", "content": "x"}])


def test_provider_selection():
    assert isinstance(build_llm(Settings(llm_provider="groq", groq_api_key="k")), GroqLLM)
    with pytest.raises(ValueError):
        build_llm(Settings(llm_provider="nope"))
