from __future__ import annotations

from pathlib import Path


class PublishError(RuntimeError):
    def __init__(self, message: str, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent  # True = retrying won't help (bad credentials, rejected content)


class Publisher:
    name = "base"
    label = "Base"
    max_chars = 500
    image_required = False        # can't post without an image
    needs_public_image_url = False  # platform fetches the image from a URL instead of an upload
    hashtags = "2-3 relevant hashtags at the end"
    audience = ""
    style_notes = ""
    secrets: tuple[str, ...] = ()
    image_size: tuple[int, int] | None = None   # exact crop (w, h); None = keep aspect ratio
    max_image_bytes = 5_000_000
    max_images = 1                # the ad + (max_images - 1) extra project photos

    def __init__(self, config: dict):
        self.config = config

    @classmethod
    def configured(cls) -> bool:
        from ..config import env

        return all(env(s) for s in cls.secrets)

    def publish(self, post: dict, image_path: Path | None, image_url: str | None, extra_paths: list[Path] = ()) -> dict:
        """Post it (ad image first, then any extra photos). Returns {"id": ..., "url": ...}."""
        raise NotImplementedError

    def fetch_metrics(self, record: dict) -> dict | None:
        """Return {"likes", "reposts", "replies"} for a published post, or None if unsupported."""
        return None
