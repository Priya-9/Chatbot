"""Claude (Anthropic) LLM integration."""

import logging
from dataclasses import dataclass
from typing import Protocol

import anthropic

from app.config import Settings

log = logging.getLogger(__name__)


@dataclass
class LLMResult:
    text: str
    refused: bool = False


class LLMError(Exception):
    """Raised when the model could not be reached; callers show a friendly fallback message."""


class LLM(Protocol):
    def complete(self, system: str, messages: list[dict]) -> LLMResult: ...


class ClaudeLLM:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key or None,  # None -> SDK resolves credentials from the environment
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )

    def complete(self, system: str, messages: list[dict]) -> LLMResult:
        params = dict(
            model=self.settings.llm_model,
            max_tokens=self.settings.llm_max_tokens,
            # The system prompt is static, so it is marked cacheable; per-request data goes in `messages`.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            output_config={"effort": self.settings.llm_effort},
        )
        try:
            if self.settings.llm_fallbacks:
                # If a safety classifier declines, the API re-runs the request on a fallback model server-side.
                response = self.client.beta.messages.create(
                    **params, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                )
            else:
                response = self.client.messages.create(**params)
        except anthropic.RateLimitError as exc:
            log.warning("Claude rate limited (request id %s)", exc.request_id)
            raise LLMError("rate_limited") from exc
        except anthropic.APIStatusError as exc:
            log.error("Claude API error %s (request id %s): %s", exc.status_code, exc.request_id, exc.message)
            raise LLMError("api_error") from exc
        except anthropic.APIConnectionError as exc:
            log.error("Could not reach Claude API: %s", exc)
            raise LLMError("connection_error") from exc

        if response.stop_reason == "refusal":
            log.info("Claude declined the request (request id %s)", response._request_id)
            return LLMResult(text="", refused=True)

        text = "".join(block.text for block in response.content if block.type == "text").strip()
        usage = response.usage
        log.debug(
            "Claude usage: in=%s out=%s cache_read=%s",
            usage.input_tokens, usage.output_tokens, usage.cache_read_input_tokens,
        )
        return LLMResult(text=text)
