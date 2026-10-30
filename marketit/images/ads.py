"""Minimal ad graphics for LEGO Ideas projects.

The project's own photos from its LEGO Ideas page are shown exactly as published: whole,
uncropped, with nothing drawn over them. They are only scaled to fit.
Around them: quiet typography, lots of white space, one accent colour.

Templates (1080 px wide; height follows the platform, e.g. 1350 for 4:5 feeds):
  milestone_ad  - "1,000 supporters"
  countdown_ad  - "7 days left"
  progress_ad   - headline + live stats
  gallery_ad    - up to three photos + headline
Every ad ends with "Support it on LEGO Ideas" and the project link.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .. import legoideas

W = 1080
M = 80  # outer margin
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

PAPER = (250, 249, 246)
INK = (17, 17, 17)
MUTED = (112, 112, 108)
LINE = (226, 224, 218)
ACCENT = (255, 199, 0)     # LEGO-ish yellow, used sparingly
URGENT = (214, 40, 28)

FONTS = {
    "display-bold": "InterDisplay-Bold.otf",
    "display-semi": "InterDisplay-SemiBold.otf",
    "display-medium": "InterDisplay-Medium.otf",
    "semi": "Inter-SemiBold.otf",
    "medium": "Inter-Medium.otf",
}

FOOTER_H = 132
PROGRESS_H = 74


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
    """Drop characters the font can't draw (emoji etc.)."""
    return " ".join("".join(ch for ch in (text or "") if ord(ch) < 0x2500 or ch in "—–…’“”").split())


# Typography ---------------------------------------------------------------------------

def tracking(fnt: ImageFont.FreeTypeFont, em: float) -> float:
    return fnt.size * em


def text_w(draw, text, fnt, track_em=0.0):
    return draw.textlength(text, font=fnt) + tracking(fnt, track_em) * max(0, len(text) - 1)


def draw_text(draw, xy, text, fnt, fill, track_em=0.0, anchor="ls"):
    """Text with tracking (letter spacing); negative tracking tightens large display type.
    anchor: 'ls' (left baseline) or 'rs' (right baseline)."""
    x, y = xy
    if anchor == "rs":
        x -= text_w(draw, text, fnt, track_em)
    if not track_em:
        draw.text((x, y), text, font=fnt, fill=fill, anchor="ls")
        return
    step = tracking(fnt, track_em)
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill, anchor="ls")
        x += draw.textlength(ch, font=fnt) + step


def eyebrow(draw, xy, text, fill=MUTED, anchor="ls", dot=None):
    """Small uppercase label with wide tracking, optionally led by a coloured dot."""
    fnt = font("semi", 22)
    x, y = xy
    if dot and anchor == "ls":
        draw.ellipse([x, y - 15, x + 12, y - 3], fill=dot)
        x += 24
    draw_text(draw, (x, y), text.upper(), fnt, fill, 0.14, anchor)


def ellipsize(draw, text, fnt, max_w, track_em=0.0):
    if text_w(draw, text, fnt, track_em) <= max_w:
        return text
    while text and text_w(draw, text + "…", fnt, track_em) > max_w:
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
    """Wrap, then narrow the measure as far as possible without adding a line, so lines are
    similar in length (no single orphaned word on the last line)."""
    lines = wrap(draw, text, fnt, max_w, track_em)
    if len(lines) < 2:
        return lines
    lo, hi = max_w * 0.5, max_w
    while hi - lo > 4:
        mid = (lo + hi) / 2
        if len(wrap(draw, text, fnt, mid, track_em)) == len(lines) and all(
                text_w(draw, l, fnt, track_em) <= mid for l in wrap(draw, text, fnt, mid, track_em)):
            hi = mid
        else:
            lo = mid
    return wrap(draw, text, fnt, hi, track_em)


def fit_headline(draw, text, max_w, max_lines=2, start=68, minimum=46, name="display-semi", track_em=-0.02):
    for size in range(start, minimum - 1, -2):
        fnt = font(name, size)
        lines = wrap(draw, text, fnt, max_w, track_em)
        if len(lines) <= max_lines and all(text_w(draw, l, fnt, track_em) <= max_w for l in lines):
            return fnt, balanced_wrap(draw, text, fnt, max_w, track_em)
    fnt = font(name, minimum)
    lines = wrap(draw, text, fnt, max_w, track_em)[:max_lines]
    lines[-1] = ellipsize(draw, lines[-1], fnt, max_w, track_em)
    return fnt, lines


# Photos (never cropped) -----------------------------------------------------------------

def scale_to_fit(photo: Image.Image, max_w: float, max_h: float) -> Image.Image:
    ratio = min(max_w / photo.width, max_h / photo.height)
    size = (max(1, round(photo.width * ratio)), max(1, round(photo.height * ratio)))
    return photo.resize(size, Image.LANCZOS) if size != photo.size else photo


def place_photo(base, photo, box):
    """Scale the whole photo into box (no cropping), centred horizontally and sitting on the
    box's bottom edge, so it stays close to the text below; spare height becomes space above."""
    x0, y0, x1, y1 = box
    im = scale_to_fit(photo, x1 - x0, y1 - y0)
    base.paste(im.convert("RGB"), (x0 + (x1 - x0 - im.width) // 2, y1 - im.height))


def justified_row(photos, width, gap, max_h):
    """Scale photos to one shared height so they fill `width`, uncropped."""
    ratio_sum = sum(p.width / p.height for p in photos)
    h = min(max_h, (width - gap * (len(photos) - 1)) / ratio_sum)
    return [p.resize((max(1, round(h * p.width / p.height)), max(1, round(h))), Image.LANCZOS) for p in photos], round(h)


# Shared blocks --------------------------------------------------------------------------------

def header(draw, project, kind_label, dot=None):
    eyebrow(draw, (M, M + 18), f"LEGO Ideas  ·  {kind_label}", dot=dot)
    if project.get("days_left") is not None:
        eyebrow(draw, (W - M, M + 18), f"{project['days_left']} days left", anchor="rs")
    return M + 52


def progress_line(draw, y, supporters):
    """Hairline track toward 10,000 with stage ticks."""
    eyebrow(draw, (M, y + 16), "Road to LEGO review")
    if supporters is not None:
        draw_text(draw, (W - M, y + 16), f"{fmt(supporters)} / 10,000", font("semi", 22), INK, anchor="rs")
    ty = y + 38
    draw.rounded_rectangle([M, ty, W - M, ty + 6], radius=3, fill=LINE)
    progress = legoideas.stage_progress(supporters)
    if progress > 0:
        draw.rounded_rectangle([M, ty, M + max(6, (W - 2 * M) * progress), ty + 6], radius=3, fill=ACCENT)
    tick_f = font("medium", 18)
    for i, stage in enumerate(legoideas.STAGES):
        x = M + (W - 2 * M) * (i + 1) / 4
        reached = supporters is not None and supporters >= stage
        draw.rectangle([x - 1, ty - 4, x + 1, ty + 10], fill=INK if reached else MUTED)
        label = compact(stage)
        lx = x - (text_w(draw, label, tick_f) if i == 3 else text_w(draw, label, tick_f) / 2)
        draw_text(draw, (lx, ty + 34), label, tick_f, INK if reached else MUTED)


def footer(draw, y, url):
    """Hairline divider, then 'Support it on LEGO Ideas' with the link and a quiet button."""
    draw.line([M, y, W - M, y], fill=LINE, width=2)
    draw_text(draw, (M, y + 62), "Support it on LEGO Ideas", font("display-semi", 36), INK, -0.01)
    draw_text(draw, (M, y + 102), f"Free to support  ·  {legoideas.short_url(url)}", font("medium", 24), MUTED)
    label = "Support  →"
    bf = font("semi", 26)
    bw = text_w(draw, label, bf) + 64
    bx1, by0 = W - M, y + 36
    draw.rounded_rectangle([bx1 - bw, by0, bx1, by0 + 68], radius=34, fill=INK)
    draw.text((bx1 - bw / 2, by0 + 34), label, font=bf, fill=PAPER, anchor="mm")


def byline(draw, y, project, size=28):
    title = clean(project.get("title") or "")
    by = f"{title}  ·  by {project['creator']}" if project.get("creator") else title
    fnt = font("medium", size)
    draw_text(draw, (M, y), ellipsize(draw, by, fnt, W - 2 * M), fnt, MUTED)


def _require(photos):
    if not photos:
        raise NoPhotosError("no project photos found on the LEGO Ideas page")


def _canvas(h):
    return Image.new("RGB", (W, h), PAPER)


def _layout_bottom(h):
    """Fixed positions for the footer and progress line, measured from the bottom."""
    footer_y = h - M - FOOTER_H + 20
    progress_y = footer_y - 44 - PROGRESS_H
    return footer_y, progress_y


# Templates --------------------------------------------------------------------------------

def _number_ad(photos, project, number_text, unit, note, h, kind_label, dot, number_color=INK):
    _require(photos)
    base = _canvas(h)
    draw = ImageDraw.Draw(base)
    footer_y, progress_y = _layout_bottom(h)
    byline_y = progress_y - 46
    number_base = byline_y - (86 if "," in number_text else 66)
    note_y = number_base - 156
    top = header(draw, project, kind_label, dot)
    place_photo(base, photos[0], (M, top, W - M, note_y - 56))

    eyebrow(draw, (M, note_y), note, fill=INK, dot=dot)
    number_f = font("display-bold", 168)
    draw_text(draw, (M - 6, number_base), number_text, number_f, number_color, -0.035)
    nw = text_w(draw, number_text, number_f, -0.035)
    draw_text(draw, (M + nw + 20, number_base), unit, font("display-medium", 54), MUTED, -0.01)
    byline(draw, byline_y, project)
    progress_line(draw, progress_y, project.get("supporters"))
    footer(draw, footer_y, project.get("url", ""))
    return base


def milestone_ad(photos, project, milestone: int, h=1350) -> Image.Image:
    note = {
        100: "First milestone reached",
        1000: "Extra time unlocked",
        5000: "Halfway to LEGO review",
        10000: "Headed to LEGO review",
    }.get(milestone, "Thank you, supporters")
    info = dict(project)
    if info.get("supporters") is None:
        info["supporters"] = milestone
    if milestone >= 10000:
        info["days_left"] = None
    return _number_ad(photos, info, fmt(milestone), "supporters", note, h, "Milestone", ACCENT)


def countdown_ad(photos, project, days_left: int, h=1350) -> Image.Image:
    goal = legoideas.next_milestone(project.get("supporters"))
    info = dict(project, days_left=None)   # the big number already says it
    unit = "day left" if days_left == 1 else "days left"
    return _number_ad(photos, info, fmt(days_left), unit, f"Help it reach {goal:,} supporters", h,
                      "Countdown", URGENT, number_color=URGENT)


def _stats_row(draw, y, project):
    """Plain numbers with labels, separated by hairlines."""
    supporters, days = project.get("supporters"), project.get("days_left")
    goal = legoideas.next_milestone(supporters)
    cols = [(fmt(supporters), "supporters")]
    if supporters is not None:
        cols.append((fmt(max(0, goal - supporters)), f"to {compact(goal)}"))
    if days is not None:
        cols.append((fmt(days), "days left"))
    if len(cols) == 1:
        cols.append(("Free", "to support"))
    col_w = (W - 2 * M) / len(cols)
    vf, lf = font("display-semi", 56), font("medium", 22)
    for i, (value, label) in enumerate(cols):
        x = M + i * col_w + (32 if i else 0)
        if i:
            draw.line([M + i * col_w, y + 6, M + i * col_w, y + 94], fill=LINE, width=2)
        color = URGENT if label == "days left" and days is not None and days <= 7 else INK
        draw_text(draw, (x, y + 56), value, vf, color, -0.02)
        draw_text(draw, (x, y + 92), label, lf, MUTED)


def _headline(draw, y, hf, hlines, project):
    line_h = round(hf.size * 1.1)
    for line in hlines:
        y += line_h
        draw_text(draw, (M - 2, y), line, hf, INK, -0.02)
    byline(draw, y + 46, project)


def progress_ad(photos, project, headline: str, h=1350) -> Image.Image:
    _require(photos)
    base = _canvas(h)
    draw = ImageDraw.Draw(base)
    footer_y, progress_y = _layout_bottom(h)
    stats_y = progress_y - 40 - 100
    hf, hlines = fit_headline(draw, clean(headline) or clean(project.get("title", "")), W - 2 * M)
    head_y = stats_y - 36 - (round(hf.size * 1.1) * len(hlines) + 50)

    top = header(draw, project, "Fan-designed set")
    place_photo(base, photos[0], (M, top, W - M, head_y - 24))
    _headline(draw, head_y, hf, hlines, project)
    _stats_row(draw, stats_y, project)
    progress_line(draw, progress_y, project.get("supporters"))
    footer(draw, footer_y, project.get("url", ""))
    return base


def gallery_ad(photos, project, headline: str, h=1350) -> Image.Image:
    if len(photos) < 3:
        return progress_ad(photos, project, headline, h)
    base = _canvas(h)
    draw = ImageDraw.Draw(base)
    footer_y, progress_y = _layout_bottom(h)
    hf, hlines = fit_headline(draw, clean(headline) or clean(project.get("title", "")), W - 2 * M, start=60, minimum=42)
    head_y = progress_y - 40 - (round(hf.size * 1.1) * len(hlines) + 50)

    top = header(draw, project, "Fan-designed set")
    avail = head_y - 28 - top
    gap = 12
    # Row 1: the main photo. Row 2: the next two side by side. All uncropped.
    row2, row2_h = justified_row(photos[1:3], W - 2 * M, gap, avail * 0.4)
    first = scale_to_fit(photos[0], W - 2 * M, avail - row2_h - gap)
    y = top + (avail - first.height - gap - row2_h)   # bottom-align the grid above the headline
    base.paste(first.convert("RGB"), (M + (W - 2 * M - first.width) // 2, y))
    y += first.height + gap
    x = M + (W - 2 * M - sum(p.width for p in row2) - gap) // 2
    for p in row2:
        base.paste(p.convert("RGB"), (x, y))
        x += p.width + gap

    _headline(draw, head_y, hf, hlines, project)
    progress_line(draw, progress_y, project.get("supporters"))
    footer(draw, footer_y, project.get("url", ""))
    return base
