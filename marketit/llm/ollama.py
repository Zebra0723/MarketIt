"""Ollama: open models running on your own machine — completely free, no key.

Only used when OLLAMA_HOST is set (e.g. http://localhost:11434), since GitHub's
runners don't have Ollama installed.
"""

from __future__ import annotations

from .. import http
from ..config import env
from .base import LLM


class OllamaLLM(LLM):
    name = "ollama"

    @classmethod
    def available(cls) -> bool:
        return bool(env("OLLAMA_HOST"))

    def complete(self, prompt, system=None, json_mode=False):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = {"model": self.model or "llama3.1", "messages": messages, "stream": False}
        if json_mode:
            body["format"] = "json"
        resp = http.post(f"{env('OLLAMA_HOST').rstrip('/')}/api/chat", json=body, timeout=300).json()
        return resp["message"]["content"]
