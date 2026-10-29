"""Pinterest API v5. Secrets: PINTEREST_ACCESS_TOKEN, PINTEREST_BOARD_ID."""

from __future__ import annotations

import base64

from .. import http
from ..config import env
from .base import Publisher, PublishError

API = "https://api.pinterest.com/v5"


class Pinterest(Publisher):
    name = "pinterest"
    label = "Pinterest"
    max_chars = 500
    image_required = True
    hashtags = "no hashtags; use searchable keywords in the description instead"
    audience = "visual search engine; great for products, crafts, gifts, LEGO builds, design, recipes; pins drive clicks for months"
    style_notes = "Keyword-rich, descriptive, helpful. Needs a short title too."
    secrets = ("PINTEREST_ACCESS_TOKEN", "PINTEREST_BOARD_ID")
    image_size = (1000, 1500)

    def _auth(self):
        return {"Authorization": f"Bearer {env('PINTEREST_ACCESS_TOKEN')}"}

    def publish(self, post, image_path, image_url):
        if not image_path:
            raise PublishError("Pinterest needs an image", permanent=True)
        body = {
            "board_id": env("PINTEREST_BOARD_ID"),
            "title": (post.get("title") or "")[:100],
            "description": post["text"][:500],
            "alt_text": post.get("alt_text", "")[:500],
            "media_source": {
                "source_type": "image_base64",
                "content_type": "image/jpeg",
                "data": base64.b64encode(image_path.read_bytes()).decode(),
            },
        }
        if post.get("link"):
            body["link"] = post["link"]
        pin = http.post(f"{API}/pins", json=body, headers=self._auth()).json()
        return {"id": pin["id"], "url": f"https://www.pinterest.com/pin/{pin['id']}/"}

    def fetch_metrics(self, record):
        pin = http.get(f"{API}/pins/{record['platform_id']}", params={"pin_metrics": "true"}, headers=self._auth()).json()
        lifetime = (pin.get("pin_metrics") or {}).get("lifetime_metrics") or {}
        if not lifetime:
            return None
        return {
            "likes": lifetime.get("reaction", 0) + lifetime.get("save", 0),
            "reposts": lifetime.get("save", 0),
            "replies": lifetime.get("comment", 0),
            "clicks": lifetime.get("outbound_click", 0),
        }
