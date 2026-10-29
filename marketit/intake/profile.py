"""Turn a link and/or manual details plus notes into a marketing profile, rules and watchers."""

from __future__ import annotations

import logging
from dataclasses import asdict

from .. import prompts
from ..llm import ask_json
from ..publishers import ALL, channel_guide, connected_channels
from ..storage import iso, now
from ..textutil import slugify
from .fetch import Page, fetch_page

log = logging.getLogger(__name__)

TRIGGER_OPS = (">=", "<=", "every", "increase")


def _num(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_watchers(raw, default_url: str | None) -> list[dict]:
    out = []
    for i, w in enumerate(raw or []):
        if not isinstance(w, dict) or not w.get("metric"):
            continue
        url = w.get("url") or default_url
        if not url or not str(url).startswith("http"):
            continue
        triggers = []
        for j, t in enumerate(w.get("triggers") or []):
            op, value = t.get("op"), _num(t.get("value"))
            if op not in TRIGGER_OPS or value is None or value <= 0:
                continue
            trig = {"id": f"t{j + 1}", "op": op, "value": value, "message": t.get("message", "")}
            if op == "increase":
                trig["window_hours"] = _num(t.get("window_hours"), 24)
            triggers.append(trig)
        out.append({
            "id": f"w{i + 1}",
            "url": url,
            "metric": str(w["metric"]).strip(),
            "every_hours": max(1.0, _num(w.get("every_hours"), 24)),
            "triggers": triggers,
            "history": [],
            "fired": [],
            "last_checked": None,
            "last_error": None,
        })
    return out


def normalize_profile(raw: dict, link: str | None, page: Page | None, manual_images: list[str]) -> tuple[dict, dict, list[dict], list[str]]:
    kind = raw.get("kind") if raw.get("kind") in prompts.KINDS else "other"
    images = list(manual_images)
    if page:
        images += [i for i in page.images if i not in images]
    profile = {
        "kind": kind,
        "title": str(raw.get("title") or (page.title if page else "") or "Untitled")[:120],
        "summary": str(raw.get("summary") or (page.description if page else ""))[:600],
        "facts": [str(f) for f in raw.get("facts") or []][:15],
        "benefits": [str(b) for b in raw.get("benefits") or []][:10],
        "audience": str(raw.get("audience") or ""),
        "tone": str(raw.get("tone") or "friendly"),
        "hashtags": [str(h).lstrip("#").replace(" ", "") for h in raw.get("hashtags") or []][:10],
        "price": raw.get("price") or (page.price if page else None),
        "link": raw.get("link") if str(raw.get("link") or "").startswith("http") else link,
        "images": images[:12],
    }
    channels = [c for c in dict.fromkeys(raw.get("channels") or []) if c in ALL] or list(ALL)
    ppw = int(min(14, max(1, _num(raw.get("posts_per_week"), 3))))
    strategy = {
        "channels": channels,
        "posts_per_week": ppw,
        "rules": [str(r) for r in raw.get("rules") or []],
        "end_date": raw.get("end_date") if raw.get("end_date") else None,
    }
    watchers = normalize_watchers(raw.get("watchers"), profile["link"] or link)
    unsupported = [str(u) for u in raw.get("unsupported") or []]
    return profile, strategy, watchers, unsupported


def build_item(llm, config: dict, *, link: str | None, notes: str = "", manual: str = "",
               image_mode: str = "auto", manual_images: list[str] | None = None,
               source: dict | None = None, existing: dict | None = None) -> dict:
    page = fetch_page(link) if link else None
    page_dict = None
    if page:
        page_dict = asdict(page)
        page_dict["images"] = page_dict["images"][:5]
    raw = ask_json(
        llm,
        prompts.profile_prompt(link, page_dict, notes, manual, channel_guide(), connected_channels(config),
                               now().date().isoformat(), image_mode),
        system=prompts.SYSTEM,
    )
    profile, strategy, watchers, unsupported = normalize_profile(raw, link, page, manual_images or [])

    item = existing or {
        "id": None,
        "status": "active",
        "created_at": iso(),
        "last_posted": {},
        "post_count": 0,
    }
    if existing:
        # Keep progress on watchers the owner still wants (same page + metric).
        old = {(w["url"], w["metric"].lower()): w for w in existing.get("watchers", [])}
        for w in watchers:
            prev = old.get((w["url"], w["metric"].lower()))
            if prev:
                w.update(history=prev.get("history", []), fired=prev.get("fired", []),
                         last_checked=prev.get("last_checked"))
        if item.get("status") == "error":
            item["status"] = "active"
    item.update(
        source=source or {"type": "link" if link else "manual", "link": link},
        image_mode=image_mode,
        notes=notes,
        manual=manual,
        profile=profile,
        strategy=strategy,
        watchers=watchers,
        unsupported=unsupported,
    )
    if not item["id"]:
        prefix = f"{source['issue']}-" if source and source.get("issue") else ""
        item["id"] = prefix + slugify(profile["title"])
    return item
