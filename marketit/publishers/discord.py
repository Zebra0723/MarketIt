"""Discord via a channel webhook. Secret: DISCORD_WEBHOOK_URL
(Server Settings → Integrations → Webhooks → New Webhook → Copy URL)."""

from __future__ import annotations

import json

from .. import http
from ..config import env
from .base import Publisher, PublishError


class Discord(Publisher):
    name = "discord"
    label = "Discord"
    max_chars = 2000
    hashtags = "no hashtags"
    audience = "your own server's members only (does not find new people)"
    style_notes = "Casual community announcement. Can use **bold** and emoji."
    secrets = ("DISCORD_WEBHOOK_URL",)
    max_image_bytes = 8_000_000
    max_images = 4

    def publish(self, post, image_path, image_url, extra_paths=()):
        url = env("DISCORD_WEBHOOK_URL") + "?wait=true"
        payload = {"content": post["text"][:2000], "allowed_mentions": {"parse": []}}
        try:
            if image_path:
                resp = http.post(
                    url,
                    data={"payload_json": json.dumps(payload)},
                    files={f"files[{i}]": (p.name, p.read_bytes(), "image/jpeg")
                           for i, p in enumerate([image_path, *extra_paths][:4])},
                ).json()
            else:
                resp = http.post(url, json=payload).json()
        except http.HTTPError as exc:
            raise PublishError(f"Discord webhook failed ({exc.status})", permanent=exc.status in (401, 404)) from None
        return {"id": resp.get("id"), "url": None}
