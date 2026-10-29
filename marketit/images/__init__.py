"""Pick or make the image for a post, then size it for the platform.

Image modes (per item):
  link  - photos found at the item's link (or listed in a manual item)
  ai    - AI-generated promo art
  auto  - real photos when there are any (sometimes as a branded card), AI art otherwise
"""

from __future__ import annotations

import io
import logging
import random
from pathlib import Path

from PIL import Image, ImageOps

from .. import http
from ..config import ROOT
from ..storage import data_dir, media_dir, now
from . import ai_gen, cards

log = logging.getLogger(__name__)


def load_image(src: str) -> Image.Image | None:
    """Load a photo from a URL or a repo-relative path. Returns None if unusable."""
    try:
        if src.startswith("http"):
            raw = http.get(src, timeout=30).content
        else:
            path = Path(src)
            raw = (path if path.is_absolute() else ROOT / path).read_bytes()
        im = Image.open(io.BytesIO(raw))
        im.load()
        im = ImageOps.exif_transpose(im).convert("RGB")
    except Exception as exc:
        log.info("skipping image %s: %s", src, exc)
        return None
    if min(im.size) < 250:
        return None
    return im


def first_photo(item: dict, offset: int = 0) -> Image.Image | None:
    photos = item["profile"].get("images") or []
    for i in range(len(photos)):
        im = load_image(photos[(offset + i) % len(photos)])
        if im:
            return im
    return None


def fit_for_platform(im: Image.Image, size: tuple[int, int] | None, max_bytes: int) -> bytes:
    if size:
        im = ImageOps.fit(im, size, Image.LANCZOS)
    else:
        im = im.copy()
        im.thumbnail((2000, 2000), Image.LANCZOS)
    for quality in (90, 82, 74, 66, 58, 50):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        if buf.tell() <= max_bytes:
            return buf.getvalue()
        if quality == 66:
            im.thumbnail((int(im.width * 0.75), int(im.height * 0.75)), Image.LANCZOS)
    return buf.getvalue()


def make_base_image(item: dict, post: dict, config: dict, rng: random.Random) -> Image.Image | None:
    """The image before platform sizing, following the item's image mode."""
    mode = item.get("image_mode", "auto")
    offset = item.get("post_count", 0)
    profile = item["profile"]
    headline = post.get("image_headline") or profile.get("title", "")
    milestone = post.get("kind") == "milestone"

    if mode in ("link", "auto"):
        photo = first_photo(item, offset)
        if photo:
            if milestone:
                return cards.milestone_card(photo, post.get("milestone_label", headline), profile.get("title", ""))
            if mode == "auto" and rng.random() < 0.3:
                return cards.promo_card(photo, headline, profile.get("price"))
            return photo
        if mode == "link":
            return cards.promo_card(None, headline, profile.get("price"))

    art = None
    if post.get("image_prompt"):
        art = ai_gen.generate(post["image_prompt"], config, seed=rng.randint(1, 10**6))
    if milestone:
        return cards.milestone_card(art, post.get("milestone_label", headline), profile.get("title", ""))
    if art:
        return art
    return cards.promo_card(None, headline, profile.get("price"))


def prepare_post_image(item: dict, post: dict, publisher, config: dict, rng: random.Random | None = None) -> str | None:
    """Create the image file for a queued post. Returns its path relative to data/."""
    rng = rng or random.Random()
    try:
        base = make_base_image(item, post, config, rng)
    except Exception as exc:
        log.warning("image creation failed for %s: %s", item["id"], exc)
        base = None
    if base is None:
        return None
    data = fit_for_platform(base, publisher.image_size, publisher.max_image_bytes)
    out = media_dir() / f"{post['id']}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return str(out.relative_to(data_dir()))


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
