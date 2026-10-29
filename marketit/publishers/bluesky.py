"""Bluesky via the AT Protocol. Secrets: BLUESKY_HANDLE, BLUESKY_APP_PASSWORD."""

from __future__ import annotations

from datetime import datetime, timezone

from PIL import Image

from .. import http
from ..config import env
from ..textutil import HASHTAG_RE, URL_RE
from .base import Publisher, PublishError

PUBLIC_API = "https://public.api.bsky.app/xrpc"


def build_facets(text: str) -> list[dict]:
    """Links and hashtags need 'facets' (UTF-8 byte ranges) to be clickable on Bluesky."""
    facets = []

    def byte_range(start: int, end: int) -> dict:
        return {
            "byteStart": len(text[:start].encode("utf-8")),
            "byteEnd": len(text[:end].encode("utf-8")),
        }

    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip(".,!?;:")
        facets.append({
            "index": byte_range(m.start(), m.start() + len(url)),
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
        })
    for m in HASHTAG_RE.finditer(text):
        facets.append({
            "index": byte_range(m.start(), m.end()),
            "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": m.group(1)}],
        })
    return facets


class Bluesky(Publisher):
    name = "bluesky"
    label = "Bluesky"
    max_chars = 300
    hashtags = "1-3 short hashtags"
    audience = "open social network; good for reaching new people via hashtags and custom feeds (tech, art, hobbies, makers, LEGO fans)"
    style_notes = "Conversational, punchy. Under 300 characters including the link."
    secrets = ("BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD")
    max_image_bytes = 950_000

    @property
    def service(self) -> str:
        return (env("BLUESKY_SERVICE") or "https://bsky.social").rstrip("/")

    def _session(self) -> dict:
        try:
            return http.post(
                f"{self.service}/xrpc/com.atproto.server.createSession",
                json={"identifier": env("BLUESKY_HANDLE"), "password": env("BLUESKY_APP_PASSWORD")},
            ).json()
        except http.HTTPError as exc:
            raise PublishError(f"Bluesky login failed: {exc}", permanent=exc.status in (400, 401)) from exc

    def publish(self, post, image_path, image_url):
        sess = self._session()
        auth = {"Authorization": f"Bearer {sess['accessJwt']}"}
        text = post["text"]
        record = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "langs": ["en"],
        }
        facets = build_facets(text)
        if facets:
            record["facets"] = facets

        if image_path:
            blob = http.post(
                f"{self.service}/xrpc/com.atproto.repo.uploadBlob",
                data=image_path.read_bytes(),
                headers={**auth, "Content-Type": "image/jpeg"},
            ).json()["blob"]
            with Image.open(image_path) as im:
                w, h = im.size
            record["embed"] = {
                "$type": "app.bsky.embed.images",
                "images": [{"alt": post.get("alt_text", "")[:1000], "image": blob, "aspectRatio": {"width": w, "height": h}}],
            }
        elif post.get("link"):
            record["embed"] = {
                "$type": "app.bsky.embed.external",
                "external": {"uri": post["link"], "title": post.get("title", "")[:300], "description": ""},
            }

        resp = http.post(
            f"{self.service}/xrpc/com.atproto.repo.createRecord",
            json={"repo": sess["did"], "collection": "app.bsky.feed.post", "record": record},
            headers=auth,
        ).json()
        rkey = resp["uri"].rsplit("/", 1)[-1]
        return {"id": resp["uri"], "url": f"https://bsky.app/profile/{sess.get('handle', sess['did'])}/post/{rkey}"}

    def fetch_metrics(self, record):
        resp = http.get(f"{PUBLIC_API}/app.bsky.feed.getPosts", params={"uris": record["platform_id"]}).json()
        posts = resp.get("posts") or []
        if not posts:
            return None
        p = posts[0]
        return {
            "likes": p.get("likeCount", 0),
            "reposts": p.get("repostCount", 0) + p.get("quoteCount", 0),
            "replies": p.get("replyCount", 0),
        }
