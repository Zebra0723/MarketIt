"""Google Gemini via REST. Free tier: get a key at https://aistudio.google.com/apikey

Google retires model names over time. If the configured model is gone, MarketIt asks the
API which models exist and switches to the newest "flash" model automatically.
"""

from __future__ import annotations

import logging
import re

import requests

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


TIMEOUT = 240


def thinking_config(model: str) -> dict:
    """Keep reasoning short: marketing copy doesn't need deep thought, and long thinking can
    take minutes. Gemini 3+ takes a level; 2.x takes a token budget."""
    major = re.search(r"gemini-(\d+)", model)
    if major and int(major.group(1)) >= 3:
        return {"thinkingLevel": "low"}
    return {"thinkingBudget": 512}


class GeminiLLM(LLM):
    name = "gemini"
    _resolved: dict[str, str] = {}  # configured name -> working name (per process)
    _no_thinking_config: set[str] = set()  # models that rejected thinkingConfig

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

    def _generate(self, model: str, body: dict) -> dict:
        body = dict(body)
        config = dict(body.get("generationConfig", {}))
        if model not in self._no_thinking_config:
            config["thinkingConfig"] = thinking_config(model)
        if config:
            body["generationConfig"] = config
        url = f"{BASE}/models/{model}:generateContent"
        for attempt in (1, 2):
            try:
                return http.post(url, json=body, headers=self._headers(), timeout=TIMEOUT).json()
            except requests.Timeout:
                if attempt == 2:
                    raise LLMError(f"Gemini ({model}) took longer than {TIMEOUT}s twice")
                log.warning("Gemini timed out; retrying once")
            except http.HTTPError as exc:
                if exc.status == 400 and "thinking" in str(exc).lower() and "thinkingConfig" in config:
                    # This model doesn't accept the thinking setting: send without it.
                    self._no_thinking_config.add(model)
                    config.pop("thinkingConfig")
                    body["generationConfig"] = config
                    continue
                raise

    def complete(self, prompt, system=None, json_mode=False):
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            body["generationConfig"] = {"responseMimeType": "application/json"}
        configured = self.model or "gemini-3.8-flash"
        model = self._resolved.get(configured, configured)
        try:
            resp = self._generate(model, body)
        except http.HTTPError as exc:
            if exc.status != 404:
                raise
            newer = self._discover()
            log.warning("Gemini model %s is unavailable; using %s (update llm.models.gemini in config.yaml)", model, newer)
            self._resolved[configured] = newer
            resp = self._generate(newer, body)
        try:
            parts = resp["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError):
            raise LLMError(f"Gemini returned no text: {str(resp)[:300]}")
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))
