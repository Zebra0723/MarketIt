"""Google Gemini via REST. Free tier: get a key at https://aistudio.google.com/apikey

Google retires model names over time. If the configured model is gone, MarketIt asks the
API which models exist and switches to the newest "flash" model automatically.
"""

from __future__ import annotations

import logging
import re
import time

import requests

from .. import http
from ..config import env
from .base import LLM, LLMError

log = logging.getLogger(__name__)
BASE = "https://generativelanguage.googleapis.com/v1beta"
SKIP = ("lite", "image", "tts", "audio", "live", "embedding", "exp", "preview", "thinking", "vision")


def ranked_models(models: list[dict], allow_lite: bool = False) -> list[str]:
    """General-purpose 'flash' models that support generateContent, newest first."""
    skip = tuple(s for s in SKIP if not (allow_lite and s == "lite"))
    candidates = []
    for m in models:
        name = m.get("name", "").removeprefix("models/")
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if "flash" not in name or any(s in name for s in skip):
            continue
        version = tuple(int(x) for x in re.findall(r"\d+", name.split("flash")[0])) or (0,)
        candidates.append((version, "lite" not in name, "latest" not in name, name))
    return [c[-1] for c in sorted(candidates, reverse=True)]


def pick_model(models: list[dict]) -> str | None:
    ranked = ranked_models(models)
    return ranked[0] if ranked else None


TIMEOUT = 90       # a healthy reply takes seconds; silence this long means the model is struggling
BUSY_WAITS = (5, 15, 30)   # seconds to wait before retrying "overloaded" (429/500/503) replies


def thinking_config(model: str) -> dict:
    """Keep reasoning short: marketing copy doesn't need deep thought, and long thinking can
    take minutes. Gemini 3+ takes a level; 2.x takes a token budget."""
    major = re.search(r"gemini-(\d+)", model)
    if major and int(major.group(1)) >= 3:
        return {"thinkingLevel": "low"}
    return {"thinkingBudget": 512}


class GeminiBusy(LLMError):
    def __init__(self, model: str):
        super().__init__(f"Gemini ({model}) is overloaded right now")
        self.model = model


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

    def _alternatives(self, current: str) -> list[str]:
        try:
            resp = http.get(f"{BASE}/models", params={"pageSize": 200}, headers=self._headers()).json()
        except Exception:
            return []
        return [m for m in ranked_models(resp.get("models", []), allow_lite=True) if m != current][:2]

    def _generate(self, model: str, body: dict, patient: bool = True) -> dict:
        body = dict(body)
        config = dict(body.get("generationConfig", {}))
        if model not in self._no_thinking_config:
            config["thinkingConfig"] = thinking_config(model)
        if config:
            body["generationConfig"] = config
        url = f"{BASE}/models/{model}:generateContent"
        busy = 0
        while True:
            try:
                return http.post(url, json=body, headers=self._headers(), timeout=TIMEOUT).json()
            except requests.Timeout as exc:
                log.warning("Gemini %s gave no answer within %ss", model, TIMEOUT)
                raise GeminiBusy(model) from exc
            except http.HTTPError as exc:
                if exc.status in (429, 500, 503):
                    if patient and busy < len(BUSY_WAITS):
                        log.warning("Gemini %s is busy (%s); retrying in %ss", model, exc.status, BUSY_WAITS[busy])
                        time.sleep(BUSY_WAITS[busy])
                        busy += 1
                        continue
                    raise GeminiBusy(model) from exc
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
        except GeminiBusy:
            resp = None
            for alt in self._alternatives(model):
                log.warning("Gemini %s is overloaded; trying %s", model, alt)
                try:
                    resp = self._generate(alt, body, patient=False)
                    break
                except (GeminiBusy, http.HTTPError):
                    continue
            if resp is None:
                raise LLMError(f"Gemini is overloaded right now (tried {model} and alternatives); will retry later")
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
