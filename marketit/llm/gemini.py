"""Google Gemini via REST. Free tier: get a key at https://aistudio.google.com/apikey"""

from __future__ import annotations

from .. import http
from ..config import env
from .base import LLM, LLMError

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiLLM(LLM):
    name = "gemini"

    @classmethod
    def available(cls) -> bool:
        return bool(env("GEMINI_API_KEY"))

    def complete(self, prompt, system=None, json_mode=False):
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            body["generationConfig"] = {"responseMimeType": "application/json"}
        resp = http.post(
            API.format(model=self.model or "gemini-2.5-flash"),
            json=body,
            headers={"x-goog-api-key": env("GEMINI_API_KEY")},
            timeout=120,
        ).json()
        try:
            parts = resp["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError):
            raise LLMError(f"Gemini returned no text: {str(resp)[:300]}")
        return "".join(p.get("text", "") for p in parts)
