"""Ad graphics in the style of a LEGO Ideas project page — clearly a fan post, never official.

Look: bright LEGO-yellow backdrop with a stud pattern, a white rounded "project card" like a
LEGO Ideas tile, chunky rounded type (Fredoka for headings, Nunito for text), a blue Support
button and a supporter progress bar. No LEGO logos or LEGO typefaces (trademarked / proprietary);
every ad says "Fan project".

The project's own photos are shown exactly as published: whole, uncropped, nothing drawn on them.

Templates (1080 px wide; height follows the platform, e.g. 1350 for 4:5 feeds):
  milestone_ad  - "1,000 SUPPORTERS" celebration ribbon
  countdown_ad  - "7 days left" on a red backdrop
  progress_ad   - project card with headline and live stats
  gallery_ad    - project card with three photos
"""

from __future__ import annotations

import hashlib
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .. import legoideas

W = 1080
M = 56                 # backdrop margin around the card
PAD = 44               # padding inside the card
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

YELLOW = (255, 207, 0)
YELLOW_DARK = (240, 186, 0)
RED = (227, 0, 11)
RED_DARK = (196, 0, 9)
BLUE = (0, 109, 183)
BLUE_DARK = (0, 84, 145)
NAVY = (26, 28, 58)
GREY = (110, 112, 128)
LIGHT = (241, 242, 246)
WHITE = (255, 255, 255)
GREEN = (0, 146, 71)
BRICKS = [RED, BLUE, GREEN, WHITE, (255, 128, 0), NAVY]

FONTS = {
    "title": "fredoka-latin-700-normal.woff",
    "title-semi": "fredoka-latin-600-normal.woff",
    "body": "nunito-latin-700-normal.woff",
    "body-bold": "nunito-latin-800-normal.woff",
    "body-black": "nunito-latin-900-normal.woff",
}


class NoPhotosError(ValueError):
    pass


@lru_cache(maxsize=128)
def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / FONTS[name]), size)


def fmt(n) -> str:
    return "—" if n is None else f"{int(n):,}"


def compact(n: int) -> str:
    return f"{n // 1000}K" if n >= 1000 and n % 1000 == 0 else f"{n:,}"


def clean(text: str) -> str:
    """Drop characters the fonts can't draw (emoji etc.)."""
    return " ".join("".join(ch for ch in (text or "") if ord(ch) < 0x0250 or ch in "—–…’“”").split())


# Text helpers ---------------------------------------------------------------------------

def text_w(draw, text, fnt, track_em=0.0):
    return draw.textlength(text, font=fnt) + fnt.size * track_em * max(0, len(text) - 1)


def draw_text(draw, xy, text, fnt, fill, track_em=0.0, anchor="ls"):
    x, y = xy
    if anchor == "rs":
        x -= text_w(draw, text, fnt, track_em)
    elif anchor == "ms":
        x -= text_w(draw, text, fnt, track_em) / 2
    if not track_em:
        draw.text((x, y), text, font=fnt, fill=fill, anchor="ls")
        return
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill, anchor="ls")
        x += draw.textlength(ch, font=fnt) + fnt.size * track_em


def ellipsize(draw, text, fnt, max_w):
    if draw.textlength(text, font=fnt) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=fnt) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def wrap(draw, text, fnt, max_w, track_em=0.0):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if text_w(draw, trial, fnt, track_em) <= max_w or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def balanced_wrap(draw, text, fnt, max_w, track_em=0.0):
    """Narrow the measure as far as possible without adding a line (no orphaned last word)."""
    lines = wrap(draw, text, fnt, max_w, track_em)
    if len(lines) < 2:
        return lines
    lo, hi = max_w * 0.5, max_w
    while hi - lo > 4:
        mid = (lo + hi) / 2
        trial = wrap(draw, text, fnt, mid, track_em)
        if len(trial) == len(lines) and all(text_w(draw, l, fnt, track_em) <= mid for l in trial):
            hi = mid
        else:
            lo = mid
    return wrap(draw, text, fnt, hi, track_em)


def fit_headline(draw, text, max_w, max_lines=2, start=60, minimum=40, name="title", track_em=0.0):
    for size in range(start, minimum - 1, -2):
        fnt = font(name, size)
        lines = wrap(draw, text, fnt, max_w, track_em)
        if len(lines) <= max_lines and all(text_w(draw, l, fnt, track_em) <= max_w for l in lines):
            return fnt, balanced_wrap(draw, text, fnt, max_w, track_em)
    fnt = font(name, minimum)
    lines = wrap(draw, text, fnt, max_w, track_em)[:max_lines]
    lines[-1] = ellipsize(draw, lines[-1], fnt, max_w)
    return fnt, lines


# Shapes -----------------------------------------------------------------------------------

def stud_backdrop(size, base, dark):
    """Flat colour with a LEGO-baseplate stud pattern."""
    im = Image.new("RGB", size, base)
    d = ImageDraw.Draw(im)
    step, r = 60, 19
    for y in range(step // 2, size[1] + step, step):
        for x in range(step // 2, size[0] + step, step):
            d.ellipse([x - r, y - r + 3, x + r, y + r + 3], fill=dark)
            d.ellipse([x - r, y - r, x + r, y + r], fill=base, outline=dark, width=3)
    return im


def shadow(base, box, radius, offset=14, blur=22, alpha=90):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    x0, y0, x1, y1 = box
    ImageDraw.Draw(layer).rounded_rectangle([x0, y0 + offset, x1, y1 + offset], radius=radius, fill=(0, 0, 0, alpha))
    base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def brick(draw, x, y, w, color, outline=None):
    """A 2x1 brick seen from the front: studs on top, body below. (x, y) = top-left."""
    stud_w, stud_h, body_h = w * 0.27, w * 0.15, w * 0.42
    shade = tuple(max(0, int(c * 0.8)) for c in color[:3])
    for cx in (x + w * 0.25, x + w * 0.75):
        draw.rounded_rectangle([cx - stud_w / 2, y, cx + stud_w / 2, y + stud_h + 4], radius=3, fill=color)
    draw.rounded_rectangle([x, y + stud_h, x + w, y + stud_h + body_h], radius=max(3, w * 0.07), fill=color)
    draw.rectangle([x, y + stud_h + body_h * 0.78, x + w, y + stud_h + body_h * 0.86], fill=shade)


def brick_confetti(base, region, seed, count):
    rnd = random.Random(seed)
    x0, y0, x1, y1 = region
    if x1 - x0 < 60 or y1 - y0 < 60:
        return
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    for _ in range(count):
        w = rnd.randint(30, 50)
        piece = Image.new("RGBA", (w + 12, w + 12), (0, 0, 0, 0))
        brick(ImageDraw.Draw(piece), 6, 6, w, rnd.choice(BRICKS) + (255,))
        piece = piece.rotate(rnd.uniform(-40, 40), expand=True, resample=Image.BICUBIC)
        layer.alpha_composite(piece, (rnd.randint(x0, max(x0, x1 - piece.width)), rnd.randint(y0, max(y0, y1 - piece.height))))
    base.alpha_composite(layer)


def avatar(draw, cx, cy, r, name):
    """Round initial avatar, like the creator avatars on LEGO Ideas."""
    colors = [BLUE, RED, GREEN, (255, 128, 0), NAVY]
    c = colors[int(hashlib.md5((name or "?").encode()).hexdigest(), 16) % len(colors)]
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
    draw.text((cx, cy + 2), (name or "?")[0].upper(), font=font("title", int(r * 1.1)), fill=WHITE, anchor="mm")


def pill(draw, x, y, text, fill, fg, size=26, right=False, icon=False):
    fnt = font("body-black", size)
    tw = text_w(draw, text, fnt, 0.06)
    pad, h = int(size * 0.8), int(size * 1.9)
    iw = int(size * 1.15) if icon else 0
    total = pad * 2 + tw + (iw + size * 0.45 if icon else 0)
    if right:
        x -= total
    draw.rounded_rectangle([x, y, x + total, y + h], radius=h // 2, fill=fill)
    tx = x + pad
    if icon:
        brick(draw, tx, y + h * 0.27, iw, fg)
        tx += iw + size * 0.45
    draw_text(draw, (tx, y + h / 2 + size * 0.36), text, fnt, fg, 0.06)
    return total


# Photos (never cropped) --------------------------------------------------------------------

def scale_to_fit(photo, max_w, max_h):
    ratio = min(max_w / photo.width, max_h / photo.height)
    size = (max(1, round(photo.width * ratio)), max(1, round(photo.height * ratio)))
    return photo.resize(size, Image.LANCZOS) if size != photo.size else photo


def photo_panel(base, photos, box, gallery=False):
    """Light panel with the project's photo(s) shown whole, centred."""
    x0, y0, x1, y1 = box
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle(box, radius=24, fill=LIGHT)
    inner = (x0 + 16, y0 + 16, x1 - 16, y1 - 16)
    if gallery and len(photos) >= 3:
        gap = 12
        iw, ih = inner[2] - inner[0], inner[3] - inner[1]
        # Row 1: main photo; row 2: two more at a shared height. All uncropped.
        ratio_sum = sum(p.width / p.height for p in photos[1:3])
        row2_h = min(ih * 0.42, (iw - gap) / ratio_sum)
        row2 = [p.resize((max(1, round(row2_h * p.width / p.height)), max(1, round(row2_h))), Image.LANCZOS) for p in photos[1:3]]
        first = scale_to_fit(photos[0], iw, ih - row2_h - gap)
        total_h = first.height + gap + round(row2_h)
        y = inner[1] + (ih - total_h) // 2
        base.paste(first.convert("RGB"), (inner[0] + (iw - first.width) // 2, y))
        y += first.height + gap
        x = inner[0] + (iw - sum(p.width for p in row2) - gap) // 2
        for p in row2:
            base.paste(p.convert("RGB"), (x, y))
            x += p.width + gap
        return
    im = scale_to_fit(photos[0], inner[2] - inner[0], inner[3] - inner[1])
    base.paste(im.convert("RGB"), (inner[0] + (inner[2] - inner[0] - im.width) // 2,
                                   inner[1] + (inner[3] - inner[1] - im.height) // 2))


# Card blocks ------------------------------------------------------------------------------

def top_bar(draw, label, on_red=False):
    """Above the card: 'LEGO Ideas · fan project' badge and the kind of post."""
    fg = WHITE if on_red else NAVY
    pill(draw, M, M - 6, "LEGO IDEAS  ·  FAN PROJECT", NAVY if not on_red else WHITE, YELLOW if not on_red else RED, size=24, icon=True)
    if label:
        draw_text(draw, (W - M, M + 34), label.upper(), font("title", 30), fg, 0.04, anchor="rs")
    return M + 70


def title_block(draw, x, y, max_w, project, headline=None):
    """Title (Fredoka), creator line with avatar, optional headline. Returns y below."""
    title = clean(project.get("title") or "LEGO Ideas project")
    tf, tlines = fit_headline(draw, title, max_w, max_lines=2, start=56, minimum=38, name="title")
    line_h = round(tf.size * 1.08)
    for line in tlines:
        y += line_h
        draw_text(draw, (x, y), line, tf, NAVY)
    y += 18
    creator = project.get("creator")
    avatar(draw, x + 22, y + 22, 22, creator or "L")
    by = f"by {creator}" if creator else "a fan-designed LEGO Ideas project"
    draw_text(draw, (x + 58, y + 32), ellipsize(draw, by, font("body-bold", 28), max_w - 60), font("body-bold", 28), GREY)
    y += 50
    if headline:
        hf = font("body-bold", 30)
        hlines = wrap(draw, clean(headline), hf, max_w)[:2]
        y += 10
        for line in hlines:
            y += 38
            draw_text(draw, (x, y), line, hf, NAVY)
    return y


def stats_block(draw, x, y, max_w, project):
    """Supporters + days left, then a progress bar toward the next goal with stage pips."""
    supporters, days = project.get("supporters"), project.get("days_left")
    nf, lf = font("title", 64), font("body-black", 22)
    draw_text(draw, (x, y + 58), fmt(supporters), nf, NAVY)
    draw_text(draw, (x, y + 92), "SUPPORTERS", lf, GREY, 0.08)
    if days is not None:
        draw_text(draw, (x + max_w, y + 58), fmt(days), nf, RED if days <= 7 else NAVY, anchor="rs")
        draw_text(draw, (x + max_w, y + 92), "DAYS LEFT", lf, GREY, 0.08, anchor="rs")
    by = y + 118
    bh = 22
    draw.rounded_rectangle([x, by, x + max_w, by + bh], radius=bh // 2, fill=LIGHT)
    progress = legoideas.stage_progress(supporters)
    if progress > 0:
        draw.rounded_rectangle([x, by, x + max(bh, max_w * progress), by + bh], radius=bh // 2, fill=GREEN)
    pf = font("body-black", 20)
    for i, stage in enumerate(legoideas.STAGES):
        px = x + max_w * (i + 1) / 4
        reached = supporters is not None and supporters >= stage
        if i < 3:
            draw.ellipse([px - 9, by + bh / 2 - 9, px + 9, by + bh / 2 + 9], fill=WHITE, outline=GREEN if reached else GREY, width=4)
        label = compact(stage)
        lx = px - (text_w(draw, label, pf) if i == 3 else text_w(draw, label, pf) / 2)
        draw_text(draw, (lx, by + bh + 30), label, pf, NAVY if reached else GREY)
    return by + bh + 44


def support_button(draw, x, y, max_w, url):
    """Big blue Support button with the project link under it."""
    h = 96
    draw.rounded_rectangle([x, y + 6, x + max_w, y + h + 6], radius=h // 2, fill=BLUE_DARK)
    draw.rounded_rectangle([x, y, x + max_w, y + h], radius=h // 2, fill=BLUE)
    label = "Support on LEGO Ideas"
    bf = font("title", 42)
    tw = text_w(draw, label, bf)
    iw = 52
    start = x + (max_w - tw - iw - 20) / 2
    brick(draw, start, y + h / 2 - 20, iw, YELLOW)
    draw_text(draw, (start + iw + 20, y + h / 2 + 15), label, bf, WHITE)
    draw_text(draw, (x + max_w / 2, y + h + 46), f"It's free!  ·  {legoideas.short_url(url)}", font("body-bold", 24), GREY, anchor="ms")
    return y + h + 60


def _require(photos):
    if not photos:
        raise NoPhotosError("no project photos found on the LEGO Ideas page")


def _card(h, on_red=False):
    base = stud_backdrop((W, h), RED if on_red else YELLOW, RED_DARK if on_red else YELLOW_DARK).convert("RGBA")
    return base


# Templates ------------------------------------------------------------------------------------

STATS_H = 186
BUTTON_H = 156


def _layout(base, draw, top, title_h, gallery_photos=None):
    """Card box and the photo area that fills whatever height is left."""
    h = base.height
    card = (M, top, W - M, h - M)
    shadow(base, card, 40)
    ImageDraw.Draw(base).rounded_rectangle(card, radius=40, fill=WHITE)
    cx0, cx1 = card[0] + PAD, card[2] - PAD
    bottom = card[3] - PAD
    button_y = bottom - BUTTON_H
    stats_y = button_y - 26 - STATS_H
    title_y = stats_y - 18 - title_h
    photo_box = (cx0, card[1] + PAD, cx1, title_y - 10)
    return card, (cx0, cx1), photo_box, title_y, stats_y, button_y


def _measure_title(project, headline):
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    max_w = W - 2 * M - 2 * PAD
    tf, tl = fit_headline(probe, clean(project.get("title") or "LEGO Ideas project"), max_w, 2, 56, 38, "title")
    h = round(tf.size * 1.08) * len(tl) + 18 + 50
    if headline:
        h += 10 + 38 * len(wrap(probe, clean(headline), font("body-bold", 30), max_w)[:2])
    return h + 8


def progress_ad(photos, project, headline: str, h=1350, gallery=False) -> Image.Image:
    _require(photos)
    base = _card(h)
    draw = ImageDraw.Draw(base)
    top = top_bar(draw, "Support this set!")
    title_h = _measure_title(project, headline)
    card, (cx0, cx1), photo_box, title_y, stats_y, button_y = _layout(base, draw, top, title_h)
    draw = ImageDraw.Draw(base)
    photo_panel(base, photos, photo_box, gallery=gallery)
    title_block(draw, cx0, title_y, cx1 - cx0, project, headline)
    stats_block(draw, cx0, stats_y, cx1 - cx0, project)
    support_button(draw, cx0, button_y, cx1 - cx0, project.get("url", ""))
    return base.convert("RGB")


def gallery_ad(photos, project, headline: str, h=1350) -> Image.Image:
    return progress_ad(photos, project, headline, h, gallery=len(photos) >= 3)


def ribbon(base, y, big: str, unit: str, note: str, on_red=False):
    """Celebration banner between the top bar and the card (never over the photo)."""
    h = 156
    box = (M, y, W - M, y + h)
    fill, fg, accent = (WHITE, RED, NAVY) if on_red else (RED, WHITE, YELLOW)
    shadow(base, box, 36, offset=10, blur=16, alpha=80)
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle(box, radius=36, fill=fill)
    nf, uf = font("title", 92), font("title", 56)
    probe = text_w(draw, big, nf) + 18 + text_w(draw, unit.upper(), uf, 0.02)
    while probe > W - 2 * M - 80 and nf.size > 60:
        nf, uf = font("title", nf.size - 6), font("title", uf.size - 4)
        probe = text_w(draw, big, nf) + 18 + text_w(draw, unit.upper(), uf, 0.02)
    x = (W - probe) / 2
    draw_text(draw, (x, y + 98), big, nf, fg)
    draw_text(draw, (x + text_w(draw, big, nf) + 18, y + 98), unit.upper(), uf, fg, 0.02)
    draw_text(draw, (W / 2, y + 138), note, font("body-black", 26), accent, 0.04, anchor="ms")
    return y + h


def _celebration(photos, project, big: str, unit: str, note: str, h, on_red=False):
    _require(photos)
    base = _card(h, on_red)
    draw = ImageDraw.Draw(base)
    top = top_bar(draw, "", on_red)
    if not on_red:
        brick_confetti(base, (W // 2 + 40, M - 30, W - M, top - 4), seed=len(big) + h, count=5)
    card_top = ribbon(base, top + 6, big, unit, note, on_red) + 26
    title_h = _measure_title(project, None)
    card, (cx0, cx1), photo_box, title_y, stats_y, button_y = _layout(base, draw, card_top, title_h)
    photo_panel(base, photos, photo_box)
    draw = ImageDraw.Draw(base)
    title_block(draw, cx0, title_y, cx1 - cx0, project)
    stats_block(draw, cx0, stats_y, cx1 - cx0, project)
    support_button(draw, cx0, button_y, cx1 - cx0, project.get("url", ""))
    return base.convert("RGB")


def milestone_ad(photos, project, milestone: int, h=1350) -> Image.Image:
    note = {100: "First milestone!", 1000: "Extra time unlocked", 5000: "Halfway there!",
            10000: "Off to LEGO review!"}.get(milestone, "Thank you!")
    info = dict(project)
    if info.get("supporters") is None:
        info["supporters"] = milestone
    if milestone >= 10000:
        info["days_left"] = None
    return _celebration(photos, info, compact(milestone) if milestone >= 10000 else fmt(milestone), "supporters", note, h)


def countdown_ad(photos, project, days_left: int, h=1350) -> Image.Image:
    goal = legoideas.next_milestone(project.get("supporters"))
    info = dict(project, days_left=days_left)
    unit = "day left" if days_left == 1 else "days left"
    return _celebration(photos, info, fmt(days_left), unit, f"Help it reach {compact(goal)}", h, on_red=True)
