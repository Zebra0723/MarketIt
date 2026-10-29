"""LLM providers behind one interface, tried in order with automatic fallback."""

from __future__ import annotations

import logging

from ..textutil import extract_json
from .base import LLM, LLMError

log = logging.getLogger(__name__)


def _make(name: str, model: str | None) -> LLM | None:
    if name == "gemini":
        from .gemini import GeminiLLM as cls
    elif name == "groq":
        from .groq import GroqLLM as cls
    elif name == "ollama":
        from .ollama import OllamaLLM as cls
    elif name == "claude":
        from .claude import ClaudeLLM as cls
    elif name == "fake":
        from .fake import FakeLLM as cls
    else:
        log.warning("unknown LLM provider %r ignored", name)
        return None
    return cls(model) if cls.available() else None


class ChainLLM(LLM):
    """Tries each configured provider in turn until one answers."""

    name = "chain"

    def __init__(self, providers: list[LLM]):
        self.providers = providers

    def complete(self, prompt: str, system: str | None = None, json_mode: bool = False) -> str:
        errors = []
        for p in self.providers:
            try:
                return p.complete(prompt, system=system, json_mode=json_mode)
            except Exception as exc:  # fall through to the next provider
                log.warning("LLM %s failed: %s", p.name, exc)
                errors.append(f"{p.name}: {exc}")
        raise LLMError("all LLM providers failed — " + " | ".join(errors))


def get_llm(config: dict, force: str | None = None) -> ChainLLM:
    names = [force] if force else config["llm"]["providers"]
    models = config["llm"].get("models", {})
    providers = [p for p in (_make(n, models.get(n)) for n in names) if p]
    if not providers:
        raise LLMError(
            "No AI provider is configured. Add a free GEMINI_API_KEY (or GROQ_API_KEY, "
            "or run Ollama) — see README.md."
        )
    return ChainLLM(providers)


def ask_json(llm: LLM, prompt: str, system: str | None = None):
    """Ask for JSON; on a parse failure, ask once more."""
    reply = llm.complete(prompt, system=system, json_mode=True)
    try:
        return extract_json(reply)
    except (ValueError, TypeError):
        reply = llm.complete(
            prompt + "\n\nYour previous reply was not valid JSON. Reply with valid JSON only.",
            system=system,
            json_mode=True,
        )
        return extract_json(reply)


__all__ = ["LLM", "LLMError", "ChainLLM", "get_llm", "ask_json"]
