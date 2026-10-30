"""Images for posts: a designed ad (see ads.py) plus the project's own photos from its LEGO Ideas page.

Photos are never cropped, filtered or drawn on. Extra photos are posted as the original files
whenever the platform's size limit allows; otherwise they're only scaled down.
"""

from __future__ import annotations

import io
import logging
from functools import lru_cache

from PIL import Image, ImageOps

from .. import http
from ..storage import data_dir, media_dir, now
from . import ads

log = logging.getLogger(__name__)
DEFAULT_SIZE = (1080, 1350)   # 4:5, the best-performing feed shape


@lru_cache(maxsize=32)
def _download(src: str) -> bytes:
    return http.get(src, timeout=30).content


def load_image(src: str) -> Image.Image | None:
    """Load a photo from a URL. Returns None if it's missing, broken or too small."""
    try:
        im = Image.open(io.BytesIO(_download(src)))
        im.load()
        im = ImageOps.exif_transpose(im).convert("RGB")
    except Exception as exc:
        log.info("skipping image %s: %s", src, exc)
        return None
    if min(im.size) < 300:
        return None
    return im


def project_photos(item: dict, offset: int = 0, limit: int = 4) -> list[tuple[str, Image.Image]]:
    """Usable (url, photo) pairs, rotated so consecutive posts lead with different shots."""
    urls = item["profile"].get("images") or []
    if not urls:
        return []
    ordered = urls[offset % len(urls):] + urls[: offset % len(urls)]
    photos = []
    for url in ordered:
        im = load_image(url)
        if im:
            photos.append((url, im))
        if len(photos) >= limit:
            break
    return photos


def original_photo_bytes(url: str, im: Image.Image, max_bytes: int) -> bytes:
    """The photo file exactly as published if it's a JPEG within the limit; else a faithful re-encode."""
    raw = _download(url)
    if raw[:3] == b"\xff\xd8\xff" and len(raw) <= max_bytes:
        return raw
    return encode(im, None, max_bytes)


def project_card_info(item: dict) -> dict:
    stats = item.get("project") or {}
    return {
        "title": item["profile"].get("title"),
        "creator": stats.get("creator"),
        "supporters": stats.get("supporters"),
        "days_left": stats.get("days_left"),
        "url": item["profile"].get("link") or "",
    }


def choose_template(post: dict, photo_count: int, post_number: int) -> str:
    if post.get("kind") == "milestone":
        return "countdown" if post.get("milestone", {}).get("metric") == "days left" else "milestone"
    if photo_count >= 3 and post_number % 2 == 1:
        return "gallery"
    return "progress"


def render_ad(item: dict, post: dict, height: int = 1350, photos=None) -> Image.Image:
    offset = item.get("post_count", 0)
    photos = [im for _, im in project_photos(item, offset)] if photos is None else photos
    info = project_card_info(item)
    template = choose_template(post, len(photos), offset)
    post["template"] = template
    headline = post.get("image_headline") or info["title"] or ""
    if template == "milestone":
        m = post.get("milestone") or {}
        if m.get("value") is not None:
            info["supporters"] = int(m["value"])
        return ads.milestone_ad(photos, info, int(m.get("threshold") or info["supporters"] or 0), height)
    if template == "countdown":
        m = post.get("milestone") or {}
        days = int(m.get("value") if m.get("value") is not None else info["days_left"] or 0)
        info["days_left"] = days
        return ads.countdown_ad(photos, info, days, height)
    if template == "gallery":
        return ads.gallery_ad(photos, info, headline, height)
    return ads.progress_ad(photos, info, headline, height)


def encode(im: Image.Image, size: tuple[int, int] | None, max_bytes: int) -> bytes:
    if size:
        im = ImageOps.fit(im, size, Image.LANCZOS) if im.size != size else im
    else:
        im = im.copy()
        im.thumbnail((2400, 2400), Image.LANCZOS)
    for quality in (95, 90, 84, 76, 68, 60):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        if buf.tell() <= max_bytes:
            return buf.getvalue()
        if quality == 76:
            im.thumbnail((int(im.width * 0.8), int(im.height * 0.8)), Image.LANCZOS)
    return buf.getvalue()


def _save(post_id: str, suffix: str, data: bytes) -> str:
    out = media_dir() / f"{post_id}{suffix}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return str(out.relative_to(data_dir()))


def prepare_post_images(item: dict, post: dict, publisher) -> tuple[str, list[str]]:
    """Render the ad (sized for the platform) and add the project's own photos.

    Returns (ad path, [extra photo paths]), relative to data/. Raises ads.NoPhotosError if the
    project page had no usable photos, so nothing is posted without them.
    """
    offset = item.get("post_count", 0)
    photos = project_photos(item, offset)
    target = publisher.image_size or DEFAULT_SIZE
    height = round(ads.W * target[1] / target[0])
    ad = render_ad(item, post, height, [im for _, im in photos])
    main = _save(post["id"], "", encode(ad, target if publisher.image_size else None, publisher.max_image_bytes))

    extras = []
    room = min(3, publisher.max_images - 1)
    for i, (url, im) in enumerate(photos[:room]):
        extras.append(_save(post["id"], f"-{i + 1}", original_photo_bytes(url, im, publisher.max_image_bytes)))
    return main, extras


def prune_media(keep_days: int) -> int:
    """Delete old post images so the repo doesn't grow forever."""
    d = media_dir()
    if not d.exists():
        return 0
    cutoff = now().timestamp() - keep_days * 86400
    removed = 0
    for f in d.glob("*.jpg"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    return removed
