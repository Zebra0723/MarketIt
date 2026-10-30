"""Google Gemini via REST. Free tier: get a key at https://aistudio.google.com/apikey

Google retires model names over time. If the configured model is gone, MarketIt asks the
API which models exist and switches to the newest "flash" model automatically.
"""

from __future__ import annotations

import logging
import re

from .. import http
from ..config import env
from .base import LLM, LLMError

log = logging.getLogger(__name__)
BASE = "https://generativelanguage.googleapis.com/v1beta"
SKIP = ("lite", "image", "tts", "audio", "live", "embedding", "exp", "preview", "thinking", "vision")


def pick_model(models: list[dict]) -> str | None:
    """Newest general-purpose 'flash' model that supports generateContent."""
    candidates = []
    for m in models:
        name = m.get("name", "").removeprefix("models/")
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if "flash" not in name or any(s in name for s in SKIP):
            continue
        version = tuple(int(x) for x in re.findall(r"\d+", name.split("flash")[0])) or (0,)
        candidates.append((version, "latest" not in name, name))
    return max(candidates)[2] if candidates else None


class GeminiLLM(LLM):
    name = "gemini"
    _resolved: dict[str, str] = {}  # configured name -> working name (per process)

    @classmethod
    def available(cls) -> bool:
        return bool(env("GEMINI_API_KEY"))

    def _headers(self):
        return {"x-goog-api-key": env("GEMINI_API_KEY")}

    def _discover(self) -> str:
        resp = http.get(f"{BASE}/models", params={"pageSize": 200}, headers=self._headers()).json()
        model = pick_model(resp.get("models", []))
        if not model:
            raise LLMError("Gemini: no usable model found for this API key")
        return model

    def complete(self, prompt, system=None, json_mode=False):
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            body["generationConfig"] = {"responseMimeType": "application/json"}
        configured = self.model or "gemini-3.8-flash"
        model = self._resolved.get(configured, configured)
        try:
            resp = http.post(f"{BASE}/models/{model}:generateContent", json=body, headers=self._headers(), timeout=120).json()
        except http.HTTPError as exc:
            if exc.status != 404:
                raise
            newer = self._discover()
            log.warning("Gemini model %s is unavailable; using %s (update llm.models.gemini in config.yaml)", model, newer)
            self._resolved[configured] = newer
            resp = http.post(f"{BASE}/models/{newer}:generateContent", json=body, headers=self._headers(), timeout=120).json()
        try:
            parts = resp["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError):
            raise LLMError(f"Gemini returned no text: {str(resp)[:300]}")
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))
