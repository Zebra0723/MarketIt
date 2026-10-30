"""Mastodon. Secrets: MASTODON_BASE_URL (e.g. https://mastodon.social), MASTODON_ACCESS_TOKEN."""

from __future__ import annotations

from .. import http
from ..config import env
from .base import Publisher


class Mastodon(Publisher):
    name = "mastodon"
    label = "Mastodon"
    max_chars = 500
    hashtags = "2-4 CamelCase hashtags (Mastodon discovery is hashtag-driven)"
    audience = "federated network of niche communities (tech, open source, art, hobbies, LEGO/AFOL); dislikes hard selling"
    style_notes = "Friendly and genuine, low hype. Describe images well."
    secrets = ("MASTODON_BASE_URL", "MASTODON_ACCESS_TOKEN")
    max_image_bytes = 8_000_000
    max_images = 4

    def _base(self):
        return env("MASTODON_BASE_URL").rstrip("/")

    def _auth(self):
        return {"Authorization": f"Bearer {env('MASTODON_ACCESS_TOKEN')}"}

    def publish(self, post, image_path, image_url, extra_paths=()):
        data = {"status": post["text"], "visibility": "public"}
        if image_path:
            ids = []
            for i, path in enumerate([image_path, *extra_paths][:4]):
                media = http.post(
                    f"{self._base()}/api/v2/media",
                    headers=self._auth(),
                    files={"file": (path.name, path.read_bytes(), "image/jpeg")},
                    data={"description": (post.get("alt_text", "") if i == 0 else f"Photo {i} of {post.get('title', 'the project')}")[:1500]},
                ).json()
                ids.append(media["id"])
            data["media_ids[]"] = ids
        status = http.post(f"{self._base()}/api/v1/statuses", headers=self._auth(), data=data).json()
        return {"id": status["id"], "url": status.get("url")}

    def fetch_metrics(self, record):
        s = http.get(f"{self._base()}/api/v1/statuses/{record['platform_id']}", headers=self._auth()).json()
        return {
            "likes": s.get("favourites_count", 0),
            "reposts": s.get("reblogs_count", 0),
            "replies": s.get("replies_count", 0),
        }
