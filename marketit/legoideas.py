"""Everything specific to LEGO Ideas projects: links, page stats and milestones."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .textutil import parse_number

# Project pages live at /product-ideas/<id> (current) or /projects/<id> (older links).
PROJECT_RE = re.compile(r"https?://ideas\.lego\.com/(projects|product-ideas)/([0-9a-fA-F-]{8,})")

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


def find_project_url(text: str | None) -> str | None:
    m = PROJECT_RE.search(text or "")
    return m.group(0) if m else None


def canonical_url(url: str) -> str:
    """https://ideas.lego.com/product-ideas/<id>/updates?x=1 -> https://ideas.lego.com/product-ideas/<id>"""
    m = PROJECT_RE.match(url.strip())
    return f"https://ideas.lego.com/{m.group(1)}/{m.group(2)}" if m else url.strip()


def short_url(url: str) -> str:
    """Readable version for graphics: ideas.lego.com/product-ideas/6726571d…"""
    m = PROJECT_RE.match(url)
    if not m:
        return urlparse(url).netloc + urlparse(url).path
    return f"ideas.lego.com/{m.group(1)}/{m.group(2)[:8]}…"


def _find(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text, re.I)
    return parse_number(m.group(1)) if m else None


SUPPORTER_KEYS = r"supporters?(?:Count|Total)?|supportCount|totalSupporters|numSupporters|votes?(?:Count)?"
DAYS_KEYS = r"daysLeft|daysRemaining|remainingDays|days_left"
EXPIRY_KEYS = r"expiresAt|expirationDate|expiryDate|expireDate|expiresOn|deadline|endDate|expires_at"
CREATOR_KEYS = r"username|userName|screenName|displayName|authorName|creatorName|alias|name"
Q = r'\\?"'   # a quote, possibly escaped (data embedded inside JS strings)


def _near_project(text: str, project_id: str | None, pattern: str) -> list[re.Match]:
    """Matches of `pattern`, the ones closest after the project's id first (pages also list other projects)."""
    matches = list(re.finditer(pattern, text))
    if project_id and matches:
        anchors = [m.start() for m in re.finditer(re.escape(project_id), text)]
        if anchors:
            def distance(m):
                after = [m.start() - a for a in anchors if m.start() >= a]
                return min(after) if after else 10**9
            matches.sort(key=distance)
    return matches


def parse_structured(scripts: str, project_id: str | None = None) -> dict:
    """Exact numbers from data embedded in the page's scripts, when present."""
    from datetime import datetime, timezone

    out = {"supporters": None, "days_left": None, "creator": None}
    if not scripts:
        return out
    for m in _near_project(scripts, project_id, rf"{Q}(?:{SUPPORTER_KEYS}){Q}\s*:\s*{Q}?(\d+)"):
        out["supporters"] = int(m.group(1))
        break
    for m in _near_project(scripts, project_id, rf"{Q}(?:{DAYS_KEYS}){Q}\s*:\s*{Q}?(\d+)"):
        out["days_left"] = int(m.group(1))
        break
    if out["days_left"] is None:
        for m in _near_project(scripts, project_id, rf"{Q}(?:{EXPIRY_KEYS}){Q}\s*:\s*{Q}(\d{{4}}-\d\d-\d\d[T0-9:.+\-Z]*)"):
            try:
                end = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
                end = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
                out["days_left"] = max(0, (end - datetime.now(timezone.utc)).days)
                break
            except ValueError:
                continue
    for owner in _near_project(scripts, project_id, rf"{Q}(?:author|creator|owner|submitter|user){Q}\s*:\s*\{{"):
        window = scripts[owner.end(): owner.end() + 600]
        name = re.search(rf"{Q}(?:{CREATOR_KEYS}){Q}\s*:\s*{Q}([^\"\\]{{2,40}}){Q}", window)
        if name:
            out["creator"] = name.group(1)
            break
    return out


def project_id(url: str) -> str | None:
    m = PROJECT_RE.match(url or "")
    return m.group(2) if m else None


def parse_stats(text: str) -> dict:
    """Last-resort guess of supporters / days left from a project page's visible text."""
    n = r"(\d[\d.,]*\s?[kKmM]?)(?!\d)"
    supporters = _find(n + r"[^\d]{0,20}?\bsupporters?\b", text) or _find(r"\bsupporters?\b[^\d]{0,20}?" + n, text)
    days_left = _find(n + r"[^\d]{0,15}?\bdays?\s+(?:left|remaining|to go)\b", text) \
        or _find(r"\bdays?\s+(?:left|remaining)\b[^\d]{0,15}?" + n, text)
    creator = None   # too unreliable to guess from text ("by default" ...): structured data or the AI decide
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


def read_stats(page, llm=None) -> dict:
    """Best available stats: page data first, then the AI reading the page, then a text guess."""
    from . import prompts
    from .llm import ask_json

    stats = parse_structured(page.scripts, project_id(page.url))
    stats["source"] = "page data"
    if (stats["supporters"] is None or stats["days_left"] is None) and llm is not None:
        try:
            reply = ask_json(llm, prompts.stats_prompt(page.text))
        except Exception:
            reply = {}
        for key in ("supporters", "days_left", "creator"):
            value = reply.get(key) if isinstance(reply, dict) else None
            if stats[key] is None and value not in (None, ""):
                if key == "creator":
                    stats[key] = str(value)[:40]
                else:
                    number = value if isinstance(value, (int, float)) else parse_number(str(value))
                    if number is not None:
                        stats[key] = int(number)
                        stats["source"] = "AI"
    if stats["supporters"] is None or stats["days_left"] is None:
        guess = parse_stats(page.text)
        for key in ("supporters", "days_left"):
            if stats[key] is None and guess[key] is not None:
                stats[key] = guess[key]
                stats["source"] = "text guess"
    return stats
