from __future__ import annotations

import json
import re
import secrets

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
HASHTAG_RE = re.compile(r"(?<![\w#])#([A-Za-z0-9_]*[A-Za-z_][A-Za-z0-9_]*)")


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug[:max_len].rstrip("-")) or "item"


def new_post_id() -> str:
    return "P" + secrets.token_hex(3).upper()


def extract_json(text: str):
    """Pull the first JSON object/array out of an LLM reply (handles ```json fences)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError("no JSON found in model reply")
    start = min(starts)
    closer = "}" if text[start] == "{" else "]"
    end = text.rfind(closer)
    if end <= start:
        raise ValueError("no JSON found in model reply")
    return json.loads(text[start : end + 1])


def fit_text(text: str, limit: int, link: str | None = None) -> str:
    """Trim `text` to `limit` characters, keeping the link (if any) intact at the end."""
    text = re.sub(r"[ \t]+\n", "\n", text).strip()
    if link and link not in text:
        text = f"{text}\n\n{link}"
    if len(text) <= limit:
        return text
    tail = ""
    body = text
    if link and link in text:
        body = text.replace(link, "").strip()
        tail = f"\n\n{link}"
    room = limit - len(tail) - 1
    if room < 20:
        return text[:limit]
    cut = body[:room]
    # Prefer ending at a sentence or word boundary.
    for sep in (". ", "! ", "? ", "\n", " "):
        idx = cut.rfind(sep)
        if idx > room * 0.6:
            cut = cut[: idx + (1 if sep != " " else 0)]
            break
    return cut.rstrip() + "…" + tail


def parse_number(raw: str) -> float | None:
    """'1,234' -> 1234, '1.2k' -> 1200, '3M' -> 3_000_000."""
    raw = raw.strip().lower().replace(" ", "")
    m = re.fullmatch(r"([\d.,]+)([km]?)", raw)
    if not m:
        return None
    num, suffix = m.groups()
    if suffix:
        num = num.replace(",", ".")
    else:
        # "1,234" or "1.234" (thousands) vs "1.5"
        if re.fullmatch(r"\d{1,3}([.,]\d{3})+", num):
            num = re.sub(r"[.,]", "", num)
        else:
            num = num.replace(",", "")
    try:
        value = float(num)
    except ValueError:
        return None
    return value * {"": 1, "k": 1_000, "m": 1_000_000}[suffix]


def format_number(value: float) -> str:
    return f"{int(value):,}" if float(value).is_integer() else f"{value:,.1f}"
