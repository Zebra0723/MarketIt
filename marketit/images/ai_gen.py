"""Free AI image generation. Returns None on any failure so callers fall back to cards."""

from __future__ import annotations

import base64
import io
import logging
from urllib.parse import quote

from PIL import Image

from .. import http
from ..config import env

log = logging.getLogger(__name__)

STYLE_SUFFIX = ", high quality promotional photo style, vibrant, clean composition, no text, no watermark"


def _pollinations(prompt: str, seed: int) -> bytes:
    url = f"https://image.pollinations.ai/prompt/{quote(prompt + STYLE_SUFFIX)}"
    return http.get(url, params={"width": 1024, "height": 1024, "nologo": "true", "seed": seed}, timeout=120).content


def _cloudflare(prompt: str, seed: int) -> bytes:
    account, token = env("CLOUDFLARE_ACCOUNT_ID"), env("CLOUDFLARE_API_TOKEN")
    if not (account and token):
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN not set")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    resp = http.post(url, json={"prompt": prompt + STYLE_SUFFIX, "seed": seed}, headers={"Authorization": f"Bearer {token}"}, timeout=120)
    return base64.b64decode(resp.json()["result"]["image"])


PROVIDERS = {"pollinations": _pollinations, "cloudflare": _cloudflare}


def generate(prompt: str, config: dict, seed: int = 1) -> Image.Image | None:
    provider = config["images"].get("ai_provider", "pollinations")
    fn = PROVIDERS.get(provider)
    if not fn:
        return None
    try:
        im = Image.open(io.BytesIO(fn(prompt, seed)))
        im.load()
        return im.convert("RGB")
    except Exception as exc:
        log.warning("AI image (%s) failed: %s", provider, exc)
        return None
