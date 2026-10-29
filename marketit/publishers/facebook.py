"""Facebook Page via the Graph API. Secrets: FACEBOOK_PAGE_ID, FACEBOOK_PAGE_TOKEN."""

from __future__ import annotations

from .. import http
from ..config import env
from .base import Publisher


class Facebook(Publisher):
    name = "facebook"
    label = "Facebook Page"
    max_chars = 2000
    hashtags = "0-2 hashtags"
    audience = "your Page's followers plus shares; broad, older-skewing audience; local services do well"
    style_notes = "Warm, a bit longer, clear call to action."
    secrets = ("FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_TOKEN")
    max_image_bytes = 8_000_000

    def _api(self):
        return f"https://graph.facebook.com/{self.config['meta']['graph_version']}"

    def publish(self, post, image_path, image_url):
        page, token = env("FACEBOOK_PAGE_ID"), env("FACEBOOK_PAGE_TOKEN")
        if image_path:
            resp = http.post(
                f"{self._api()}/{page}/photos",
                data={"message": post["text"], "access_token": token, "published": "true"},
                files={"source": (image_path.name, image_path.read_bytes(), "image/jpeg")},
            ).json()
            post_id = resp.get("post_id") or resp["id"]
        else:
            data = {"message": post["text"], "access_token": token}
            if post.get("link"):
                data["link"] = post["link"]
            post_id = http.post(f"{self._api()}/{page}/feed", data=data).json()["id"]
        return {"id": post_id, "url": f"https://www.facebook.com/{post_id}"}

    def fetch_metrics(self, record):
        m = http.get(
            f"{self._api()}/{record['platform_id']}",
            params={
                "fields": "reactions.summary(total_count),comments.summary(total_count),shares",
                "access_token": env("FACEBOOK_PAGE_TOKEN"),
            },
        ).json()
        return {
            "likes": m.get("reactions", {}).get("summary", {}).get("total_count", 0),
            "reposts": m.get("shares", {}).get("count", 0),
            "replies": m.get("comments", {}).get("summary", {}).get("total_count", 0),
        }
