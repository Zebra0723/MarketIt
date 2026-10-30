"""X (Twitter) API v2, text + link only (the free tier is very limited).
Secrets: X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET. Off by default in config.yaml."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets as pysecrets
import time
from urllib.parse import quote

from .. import http
from ..config import env
from .base import Publisher, PublishError

API = "https://api.x.com/2/tweets"


def _pct(s: str) -> str:
    return quote(s, safe="~")


def oauth1_header(method: str, url: str, key: str, secret: str, token: str, token_secret: str,
                  nonce: str | None = None, timestamp: str | None = None) -> str:
    params = {
        "oauth_consumer_key": key,
        "oauth_nonce": nonce or pysecrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    param_str = "&".join(f"{_pct(k)}={_pct(v)}" for k, v in sorted(params.items()))
    base = "&".join([method.upper(), _pct(url), _pct(param_str)])
    signing_key = f"{_pct(secret)}&{_pct(token_secret)}"
    sig = base64.b64encode(hmac.new(signing_key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    params["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(params.items()))


class X(Publisher):
    name = "x"
    label = "X (Twitter)"
    max_chars = 280
    hashtags = "1-2 hashtags"
    audience = "fast-moving public feed; tech, news, gaming, crypto"
    style_notes = "Short and punchy; links count as 23 characters."
    secrets = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")

    def publish(self, post, image_path, image_url, extra_paths=()):
        auth = oauth1_header("POST", API, env("X_API_KEY"), env("X_API_SECRET"), env("X_ACCESS_TOKEN"), env("X_ACCESS_SECRET"))
        try:
            data = http.post(API, json={"text": post["text"]}, headers={"Authorization": auth}).json()["data"]
        except http.HTTPError as exc:
            raise PublishError(f"X refused the post: {exc}", permanent=exc.status in (401, 403)) from exc
        return {"id": data["id"], "url": f"https://x.com/i/web/status/{data['id']}"}
