"""Groq LLM integration (OpenAI-compatible Chat Completions API, called with httpx)."""

import logging
import time

import httpx

from app.config import Settings
from app.llm.claude import LLMError, LLMResult

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
# gpt-oss models accept low | medium | high; map the higher Claude-style levels down.
REASONING_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}


class GroqLLM:
    def __init__(self, settings: Settings, max_retries: int = 2):
        if not settings.groq_api_key:
            log.warning("GROQ_API_KEY is not set; Groq requests will fail")
        self.settings = settings
        self.max_retries = max_retries
        self.client = httpx.Client(
            base_url=settings.groq_api_base,
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            timeout=settings.llm_timeout_seconds,
        )

    def _payload(self, system: str, messages: list[dict]) -> dict:
        payload = {
            "model": self.settings.groq_model,
            "messages": [{"role": "system", "content": system}, *messages],
            "max_completion_tokens": self.settings.llm_max_tokens,
        }
        if self.settings.groq_model.startswith("openai/gpt-oss"):
            payload["reasoning_effort"] = REASONING_EFFORT.get(self.settings.llm_effort, "low")
        return payload

    def _post(self, payload: dict) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            last = attempt == self.max_retries
            try:
                response = self.client.post("/chat/completions", json=payload)
            except httpx.RequestError as exc:
                if last:
                    log.error("Could not reach Groq API: %s", exc)
                    raise LLMError("connection_error") from exc
            else:
                if response.status_code not in RETRYABLE_STATUS or last:
                    return response
            time.sleep(0.5 * 2**attempt)
        raise AssertionError("unreachable")

    def complete(self, system: str, messages: list[dict]) -> LLMResult:
        response = self._post(self._payload(system, messages))
        request_id = response.headers.get("x-request-id")
        if response.status_code == 429:
            log.warning("Groq rate limited (request id %s)", request_id)
            raise LLMError("rate_limited")
        if response.is_error:
            log.error("Groq API error %s (request id %s): %s", response.status_code, request_id, response.text[:500])
            raise LLMError("api_error")

        data = response.json()
        choice = data["choices"][0]
        if choice.get("finish_reason") == "content_filter":
            log.info("Groq declined the request (request id %s)", request_id)
            return LLMResult(text="", refused=True)

        text = (choice["message"].get("content") or "").strip()
        usage = data.get("usage") or {}
        log.debug("Groq usage: in=%s out=%s", usage.get("prompt_tokens"), usage.get("completion_tokens"))
        return LLMResult(text=text)
