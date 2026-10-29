"""Anthropic Claude — paid and optional. Needs `pip install anthropic` and ANTHROPIC_API_KEY."""

from __future__ import annotations

from ..config import env
from .base import LLM, LLMError


class ClaudeLLM(LLM):
    name = "claude"

    @classmethod
    def available(cls) -> bool:
        if not env("ANTHROPIC_API_KEY"):
            return False
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    def complete(self, prompt, system=None, json_mode=False):
        import anthropic

        client = anthropic.Anthropic()
        kwargs = {
            "model": self.model or "claude-opus-5-5",
            "max_tokens": 16000,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"effort": "medium"},
            # If a request is declined by a safety classifier, let the API retry it
            # on Anthropic's recommended fallback model instead of failing.
            "betas": ["server-side-fallback-2026-07-01"],
            "extra_body": {"fallbacks": "default"},
        }
        if system:
            kwargs["system"] = system
        try:
            response = client.beta.messages.create(**kwargs)
        except anthropic.RateLimitError as exc:
            raise LLMError(f"Claude rate limited: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Claude API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"Claude connection error: {exc}") from exc
        if response.stop_reason == "refusal":
            raise LLMError("Claude declined this request")
        return "".join(b.text for b in response.content if b.type == "text")
