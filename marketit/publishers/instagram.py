"""Instagram (business/creator account) via the Graph API.
Secrets: INSTAGRAM_USER_ID, INSTAGRAM_ACCESS_TOKEN. Needs a public image URL."""

from __future__ import annotations

import time

from .. import http
from ..config import env
from .base import Publisher, PublishError


class Instagram(Publisher):
    name = "instagram"
    label = "Instagram"
    max_chars = 2200
    image_required = True
    needs_public_image_url = True
    hashtags = "5-10 relevant hashtags at the end"
    audience = "huge visual audience; products, lifestyle, LEGO/MOC builds, creators"
    style_notes = "Hook in the first line, then story, then hashtags. Links aren't clickable: say 'link in bio' and still include the URL once."
    secrets = ("INSTAGRAM_USER_ID", "INSTAGRAM_ACCESS_TOKEN")
    image_size = (1080, 1350)
    max_image_bytes = 8_000_000

    def _api(self):
        return f"https://graph.facebook.com/{self.config['meta']['graph_version']}"

    def publish(self, post, image_path, image_url):
        if not image_url:
            raise PublishError("Instagram needs a public image URL (see media.public_base_url)", permanent=True)
        uid, token = env("INSTAGRAM_USER_ID"), env("INSTAGRAM_ACCESS_TOKEN")
        container = http.post(
            f"{self._api()}/{uid}/media",
            params={"image_url": image_url, "caption": post["text"], "access_token": token},
        ).json()["id"]
        for _ in range(10):
            status = http.get(f"{self._api()}/{container}", params={"fields": "status_code", "access_token": token}).json()
            if status.get("status_code") == "FINISHED":
                break
            if status.get("status_code") == "ERROR":
                raise PublishError("Instagram could not process the image", permanent=True)
            time.sleep(3)
        media_id = http.post(
            f"{self._api()}/{uid}/media_publish", params={"creation_id": container, "access_token": token}
        ).json()["id"]
        link = http.get(f"{self._api()}/{media_id}", params={"fields": "permalink", "access_token": token}).json().get("permalink")
        return {"id": media_id, "url": link}

    def fetch_metrics(self, record):
        m = http.get(
            f"{self._api()}/{record['platform_id']}",
            params={"fields": "like_count,comments_count", "access_token": env("INSTAGRAM_ACCESS_TOKEN")},
        ).json()
        return {"likes": m.get("like_count", 0), "reposts": 0, "replies": m.get("comments_count", 0)}
