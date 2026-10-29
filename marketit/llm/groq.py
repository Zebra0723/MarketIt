"""Groq (fast open models). Free tier: get a key at https://console.groq.com/keys"""

from __future__ import annotations

from .. import http
from ..config import env
from .base import LLM

API = "https://api.groq.com/openai/v1/chat/completions"


class GroqLLM(LLM):
    name = "groq"

    @classmethod
    def available(cls) -> bool:
        return bool(env("GROQ_API_KEY"))

    def complete(self, prompt, system=None, json_mode=False):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = {"model": self.model or "llama-3.3-70b-versatile", "messages": messages}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        resp = http.post(
            API, json=body, headers={"Authorization": f"Bearer {env('GROQ_API_KEY')}"}, timeout=120
        ).json()
        return resp["choices"][0]["message"]["content"]
