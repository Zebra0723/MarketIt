"""Template graphics drawn with Pillow — always free, always available."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

SIZE = (1080, 1080)
FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)
PALETTES = [
    ((255, 94, 58), (255, 149, 0)),
    ((88, 86, 214), (0, 122, 255)),
    ((52, 199, 89), (0, 150, 136)),
    ((255, 45, 85), (175, 82, 222)),
    ((255, 204, 0), (255, 112, 67)),
]


def font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_PATHS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def gradient(colors: tuple, size=SIZE) -> Image.Image:
    top, bottom = colors
    im = Image.new("RGB", size)
    draw = ImageDraw.Draw(im)
    for y in range(size[1]):
        t = y / size[1]
        draw.line([(0, y), (size[0], y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return im


def palette_for(text: str) -> tuple:
    return PALETTES[int(hashlib.md5(text.encode()).hexdigest(), 16) % len(PALETTES)]


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = f"{line} {w}".strip()
        if draw.textlength(trial, font=fnt) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def _fit_text(draw, text, max_width, max_lines, start=96, minimum=40):
    size = start
    while size > minimum:
        fnt = font(size)
        lines = wrap(draw, text, fnt, max_width)
        if len(lines) <= max_lines and all(draw.textlength(l, font=fnt) <= max_width for l in lines):
            return fnt, lines
        size -= 6
    fnt = font(minimum)
    return fnt, wrap(draw, text, fnt, max_width)[:max_lines]


def _background(photo: Image.Image | None, seed_text: str) -> Image.Image:
    if photo is None:
        return gradient(palette_for(seed_text))
    bg = ImageOps.fit(photo, SIZE, Image.LANCZOS)
    return bg


def promo_card(photo: Image.Image | None, headline: str, price: str | None = None) -> Image.Image:
    """Photo (or gradient) with a dark band and a bold headline."""
    im = _background(photo, headline)
    draw = ImageDraw.Draw(im, "RGBA")
    w, h = SIZE
    fnt, lines = _fit_text(draw, headline, w - 140, 3)
    line_h = fnt.size + 14
    band_h = line_h * len(lines) + 100
    draw.rectangle([0, h - band_h, w, h], fill=(0, 0, 0, 170))
    y = h - band_h + 50
    for line in lines:
        draw.text((70, y), line, font=fnt, fill="white")
        y += line_h
    if price:
        pf = font(48)
        label = f" {price} "
        tw = draw.textlength(label, font=pf)
        draw.rounded_rectangle([w - tw - 90, 50, w - 50, 130], radius=40, fill=(255, 204, 0, 240))
        draw.text((w - tw - 70, 64), label, font=pf, fill=(20, 20, 20))
    return im


def milestone_card(photo: Image.Image | None, big_text: str, subtitle: str) -> Image.Image:
    """Celebration graphic, e.g. '1,000 SUPPORTERS!' over a blurred photo."""
    if photo is not None:
        im = ImageOps.fit(photo, SIZE, Image.LANCZOS).filter(ImageFilter.GaussianBlur(6))
        overlay = Image.new("RGBA", SIZE, (0, 0, 0, 120))
        im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
    else:
        im = gradient(palette_for(subtitle or big_text))
    draw = ImageDraw.Draw(im)
    w, h = SIZE
    fnt, lines = _fit_text(draw, big_text.upper(), w - 160, 3, start=130, minimum=50)
    line_h = fnt.size + 20
    total = line_h * len(lines)
    y = (h - total) // 2 - 40
    for line in lines:
        tw = draw.textlength(line, font=fnt)
        draw.text(((w - tw) / 2, y), line, font=fnt, fill="white", stroke_width=4, stroke_fill=(0, 0, 0))
        y += line_h
    if subtitle:
        sf, slines = _fit_text(draw, subtitle, w - 160, 2, start=52, minimum=32)
        y += 30
        for line in slines:
            tw = draw.textlength(line, font=sf)
            draw.text(((w - tw) / 2, y), line, font=sf, fill=(255, 230, 120), stroke_width=2, stroke_fill=(0, 0, 0))
            y += sf.size + 10
    # confetti
    rnd = int(hashlib.md5(big_text.encode()).hexdigest(), 16)
    for i in range(60):
        rnd = (rnd * 1103515245 + 12345) & 0x7FFFFFFF
        x, yy = rnd % w, (rnd // w) % h
        if abs(yy - h // 2) < 230:
            continue
        color = PALETTES[i % len(PALETTES)][i % 2]
        draw.rectangle([x, yy, x + 14, yy + 8], fill=color)
    return im
