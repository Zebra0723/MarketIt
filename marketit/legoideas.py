"""Everything specific to LEGO Ideas projects: links, page stats and milestones."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .textutil import parse_number

PROJECT_RE = re.compile(r"https?://ideas\.lego\.com/projects/([0-9a-fA-F-]{8,})")

# Milestones that get a celebration post by default. 10,000 sends a project to LEGO review.
DEFAULT_MILESTONES = [100, 250, 500, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000]
DEFAULT_DAYS_LEFT_ALERTS = [30, 7, 1]
# The official stages, used for the progress bar and to explain what a milestone means.
STAGES = [100, 1000, 5000, 10000]
STAGE_MEANING = {
    100: "the first big hurdle on LEGO Ideas, which earns the project more time",
    1000: "a major milestone that earns the project extra time",
    5000: "halfway to LEGO review, which earns the project extra time",
    10000: "the goal: the project now goes to official LEGO review and could become a real set",
}
TITLE_SUFFIX_RE = re.compile(r"\s*[|\-–]\s*LEGO\s*Ideas.*$", re.I)
SKIP_IMAGE_HINTS = ("avatar", "profile", "logo", "badge", "icon", "sprite", "placeholder", "favicon")


def is_project_url(url: str | None) -> bool:
    return bool(url and PROJECT_RE.match(url.strip()))


def canonical_url(url: str) -> str:
    """https://ideas.lego.com/projects/<id>/updates?x=1 -> https://ideas.lego.com/projects/<id>"""
    m = PROJECT_RE.match(url.strip())
    return f"https://ideas.lego.com/projects/{m.group(1)}" if m else url.strip()


def short_url(url: str) -> str:
    """Readable version for graphics: ideas.lego.com/projects/a6b7e5c1…"""
    m = PROJECT_RE.match(url)
    if not m:
        return urlparse(url).netloc + urlparse(url).path
    return f"ideas.lego.com/projects/{m.group(1)[:8]}…"


def _find(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text, re.I)
    return parse_number(m.group(1)) if m else None


def parse_stats(text: str) -> dict:
    """Pull supporters / days left / creator from a project page's visible text."""
    n = r"(\d[\d.,]*\s?[kKmM]?)(?!\d)"
    supporters = _find(n + r"[^\d]{0,20}?\bsupporters?\b", text) or _find(r"\bsupporters?\b[^\d]{0,20}?" + n, text)
    days_left = _find(n + r"[^\d]{0,15}?\bdays?\s+(?:left|remaining|to go)\b", text) \
        or _find(r"\bdays?\s+(?:left|remaining)\b[^\d]{0,15}?" + n, text)
    creator = None
    m = re.search(r"\b(?:created\s+by|submitted\s+by|by)\s*\n?\s*@?([A-Za-z0-9_.\-]{3,30})\b", text)
    if m and m.group(1).lower() not in ("the", "lego", "your", "this"):
        creator = m.group(1)
    return {
        "supporters": int(supporters) if supporters is not None else None,
        "days_left": int(days_left) if days_left is not None else None,
        "creator": creator,
    }


def clean_title(title: str) -> str:
    return TITLE_SUFFIX_RE.sub("", title or "").strip() or "LEGO Ideas project"


def project_images(images: list[str]) -> list[str]:
    return [i for i in images if not any(h in i.lower() for h in SKIP_IMAGE_HINTS)]


def next_milestone(supporters: int | None) -> int:
    for m in DEFAULT_MILESTONES:
        if supporters is None or supporters < m:
            return m
    return 10000


def stage_progress(supporters: int | None) -> float:
    """0..1 along a track with equal-width segments 0-100, 100-1k, 1k-5k, 5k-10k."""
    if not supporters:
        return 0.0
    bounds = [0] + STAGES
    seg = 1 / len(STAGES)
    for i in range(len(STAGES)):
        lo, hi = bounds[i], bounds[i + 1]
        if supporters < hi:
            return i * seg + seg * (supporters - lo) / (hi - lo)
    return 1.0


def default_watchers(url: str, milestones: list[int], days_alerts: list[int], every_hours: float) -> list[dict]:
    return [
        {
            "url": url, "metric": "supporters", "every_hours": every_hours,
            "triggers": [{"op": ">=", "value": m, "message": STAGE_MEANING.get(m, "milestone")} for m in milestones],
        },
        {
            "url": url, "metric": "days left", "every_hours": every_hours,
            "triggers": [{"op": "<=", "value": d, "message": "countdown: time is running out"} for d in days_alerts],
        },
    ]
