"""Turn a LEGO Ideas link plus notes into a marketing profile, rules and milestone watchers."""

from __future__ import annotations

import logging
from dataclasses import asdict

from .. import legoideas, prompts
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


def project_stats(page: Page | None, title_hint: str | None = None) -> dict:
    stats = legoideas.parse_stats(page.text) if page else {"supporters": None, "days_left": None, "creator": None}
    stats["next_goal"] = legoideas.next_milestone(stats["supporters"])
    stats["updated_at"] = iso()
    return stats


def lego_watchers(link: str, config: dict, extra_milestones: list) -> list[dict]:
    lego = config.get("lego", {})
    milestones = sorted({int(m) for m in lego.get("milestones", legoideas.DEFAULT_MILESTONES)}
                        | {int(m) for m in extra_milestones if _num(m) and 0 < _num(m) <= 100000})
    raw = legoideas.default_watchers(
        link, milestones, lego.get("days_left_alerts", legoideas.DEFAULT_DAYS_LEFT_ALERTS),
        float(lego.get("check_every_hours", 6)),
    )
    return normalize_watchers(raw, link)


def build_item(llm, config: dict, *, link: str, notes: str = "", source: dict | None = None,
               existing: dict | None = None) -> dict:
    if not legoideas.is_project_url(link):
        raise ValueError("MarketIt only works with LEGO Ideas project links, like https://ideas.lego.com/product-ideas/…")
    link = legoideas.canonical_url(link)
    page = fetch_page(link)
    stats = project_stats(page)
    page_dict = asdict(page)
    page_dict["images"] = page_dict["images"][:5]
    page_dict["text"] = page_dict["text"][:6000]   # plenty for a profile; keeps the AI fast
    raw = ask_json(
        llm,
        prompts.profile_prompt(link, page_dict, stats, notes, channel_guide(), connected_channels(config),
                               now().date().isoformat()),
        system=prompts.SYSTEM,
    )

    hashtags = [str(h).lstrip("#").replace(" ", "") for h in raw.get("hashtags") or []]
    for tag in ("LEGOIdeas", "LEGO"):
        if tag.lower() not in {h.lower() for h in hashtags}:
            hashtags.insert(0, tag)
    profile = {
        "kind": "lego_ideas_project",
        "title": legoideas.clean_title(str(raw.get("title") or page.title))[:120],
        "summary": str(raw.get("summary") or page.description)[:600],
        "theme": str(raw.get("theme") or ""),
        "facts": [str(f) for f in raw.get("facts") or []][:15],
        "selling_points": [str(b) for b in raw.get("selling_points") or []][:10],
        "audience": str(raw.get("audience") or "LEGO fans"),
        "tone": str(raw.get("tone") or "enthusiastic"),
        "hashtags": hashtags[:10],
        "link": link,
        "images": legoideas.project_images(page.images)[:12],
    }
    if not stats.get("creator") and raw.get("creator"):
        stats["creator"] = str(raw["creator"])[:40]

    channels = [c for c in dict.fromkeys(raw.get("channels") or []) if c in ALL] or list(ALL)
    strategy = {
        "channels": channels,
        "posts_per_week": int(min(14, max(1, _num(raw.get("posts_per_week"), config.get("lego", {}).get("posts_per_week", 3))))),
        "rules": [str(r) for r in raw.get("rules") or []],
        "end_date": raw.get("end_date") or None,
    }
    watchers = lego_watchers(link, config, raw.get("extra_milestones") or [])

    item = existing or {"id": None, "status": "active", "created_at": iso(), "last_posted": {}, "post_count": 0}
    if existing:
        # Keep progress (readings, milestones already celebrated) on watchers that still exist.
        old = {(w["url"], w["metric"].lower()): w for w in existing.get("watchers", [])}
        for w in watchers:
            prev = old.get((w["url"], w["metric"].lower()))
            if prev:
                w.update(history=prev.get("history", []), fired=prev.get("fired", []), last_checked=prev.get("last_checked"))
        if item.get("status") == "error":
            item["status"] = "active"
    item.update(
        source=source or {"type": "link", "link": link},
        notes=notes,
        profile=profile,
        project=stats,
        strategy=strategy,
        watchers=watchers,
        unsupported=[str(u) for u in raw.get("unsupported") or []],
    )
    if not item["id"]:
        prefix = f"{source['issue']}-" if source and source.get("issue") else ""
        item["id"] = prefix + slugify(profile["title"])
    return item
