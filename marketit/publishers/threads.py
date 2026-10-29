"""Threads (Meta). Secrets: THREADS_USER_ID, THREADS_ACCESS_TOKEN.
Images must be at a public URL (see media.public_base_url in config.yaml)."""

from __future__ import annotations

import time

from .. import http
from ..config import env
from .base import Publisher, PublishError

API = "https://graph.threads.net/v1.0"


class Threads(Publisher):
    name = "threads"
    label = "Threads"
    max_chars = 500
    needs_public_image_url = True
    hashtags = "at most 1 topic tag"
    audience = "large general audience from the Instagram world; lifestyle, products, creators"
    style_notes = "Casual, conversational, invites replies."
    secrets = ("THREADS_USER_ID", "THREADS_ACCESS_TOKEN")
    max_image_bytes = 8_000_000

    def _wait_ready(self, container_id: str, token: str) -> None:
        for _ in range(10):
            status = http.get(f"{API}/{container_id}", params={"fields": "status,error_message", "access_token": token}).json()
            if status.get("status") == "FINISHED":
                return
            if status.get("status") == "ERROR":
                raise PublishError(f"Threads rejected the post: {status.get('error_message')}", permanent=True)
            time.sleep(3)

    def publish(self, post, image_path, image_url):
        uid, token = env("THREADS_USER_ID"), env("THREADS_ACCESS_TOKEN")
        params = {"text": post["text"], "access_token": token}
        if image_url:
            params.update(media_type="IMAGE", image_url=image_url)
        else:
            params["media_type"] = "TEXT"
        container = http.post(f"{API}/{uid}/threads", params=params).json()["id"]
        self._wait_ready(container, token)
        published = http.post(f"{API}/{uid}/threads_publish", params={"creation_id": container, "access_token": token}).json()
        media_id = published["id"]
        link = http.get(f"{API}/{media_id}", params={"fields": "permalink", "access_token": token}).json().get("permalink")
        return {"id": media_id, "url": link}

    def fetch_metrics(self, record):
        resp = http.get(
            f"{API}/{record['platform_id']}/insights",
            params={"metric": "likes,replies,reposts,quotes", "access_token": env("THREADS_ACCESS_TOKEN")},
        ).json()
        values = {m["name"]: (m.get("values") or [{}])[0].get("value", 0) for m in resp.get("data", [])}
        return {
            "likes": values.get("likes", 0),
            "reposts": values.get("reposts", 0) + values.get("quotes", 0),
            "replies": values.get("replies", 0),
        }
