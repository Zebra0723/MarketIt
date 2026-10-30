"""Settings: config.yaml merged over defaults, plus secrets from the environment."""

from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("MARKETIT_ROOT", Path(__file__).resolve().parent.parent))

DEFAULTS: dict = {
    "llm": {
        "providers": ["gemini", "groq", "ollama", "claude"],
        "models": {
            "gemini": "gemini-2.5-flash",
            "groq": "llama-3.3-70b-versatile",
            "ollama": "llama3.1",
            "claude": "claude-opus-5-5",
        },
    },
    "lego": {},
    "approvals": {"first_n": 5},
    "channels": {},
    "posting": {"explore_rate": 0.2, "min_hours_between_same_item": 20, "stats_every_hours": 20},
    "reddit": {"drafts": True},
    "meta": {"graph_version": "v23.0"},
    "media": {"public_base_url": None, "keep_days": 45},
    "github": {"allowed_associations": ["OWNER", "MEMBER", "COLLABORATOR"]},
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path | None = None) -> dict:
    path = path or ROOT / "config.yaml"
    data = {}
    if path.exists():
        data = yaml.safe_load(path.read_text()) or {}
    return _merge(DEFAULTS, data)


def env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


SECRET_HINTS = ("TOKEN", "PASSWORD", "SECRET", "API_KEY", "WEBHOOK")


def redact(text: str) -> str:
    """Remove secret values from text before it is logged or posted in an issue comment."""
    for name, value in os.environ.items():
        if value and len(value) >= 8 and any(h in name for h in SECRET_HINTS):
            text = text.replace(value, "***")
    return text
