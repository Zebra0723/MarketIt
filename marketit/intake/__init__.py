"""Adding items: from a GitHub issue, from the command line, or from items/*.yaml."""

from __future__ import annotations

import hashlib
import logging

import yaml

from .. import prompts
from ..config import ROOT, redact
from ..llm import ask_json
from ..publishers import ALL, connected_channels
from ..storage import all_items, find_item_by_issue, load_item, save_item
from ..planner import item_channels
from .issue_form import parse_issue_form
from .profile import build_item

log = logging.getLogger(__name__)
ITEM_LABEL = "marketit-item"


def _unique_id(item_id: str, own: str | None = None) -> str:
    taken = {i["id"] for i in all_items()} - {own}
    if item_id not in taken:
        return item_id
    n = 2
    while f"{item_id}-{n}" in taken:
        n += 1
    return f"{item_id}-{n}"


def reddit_drafts(llm, item: dict) -> list[dict]:
    try:
        reply = ask_json(llm, prompts.reddit_prompt(item), system=prompts.SYSTEM)
        return [d for d in reply.get("drafts", []) if isinstance(d, dict)][:2]
    except Exception as exc:
        log.info("reddit drafts skipped: %s", exc)
        return []


def describe_trigger(t: dict, metric: str) -> str:
    v = f"{t['value']:,.0f}"
    return {
        ">=": f"when it reaches {v} {metric}",
        "<=": f"when it drops to {v} {metric}",
        "every": f"every {v} {metric}",
        "increase": f"when it grows by {v} {metric} within {t.get('window_hours', 24):.0f}h",
    }[t["op"]] + (f" — {t['message']}" if t.get("message") else "")


def summary_markdown(item: dict, config: dict, drafts: list[dict] | None = None) -> str:
    p, s = item["profile"], item["strategy"]
    connected = connected_channels(config)
    using = item_channels(item, connected) if connected else []
    lines = [
        f"## ✅ Got it: **{p['title']}**",
        "",
        f"**What it is:** {p['kind'].replace('_', ' ')}  ",
        f"**Summary:** {p['summary']}  ",
        f"**Audience:** {p['audience']}  ",
        f"**Price:** {p['price']}  " if p.get("price") else "",
        f"**Link:** {p['link']}  " if p.get("link") else "",
        f"**Images:** {len(p.get('images', []))} found · mode `{item['image_mode']}`",
        "",
        f"**Posting:** about {s['posts_per_week']} posts/week per channel"
        + (f", until {s['end_date']}" if s.get("end_date") else ""),
        f"**Channels:** {', '.join(ALL[c].label for c in using)}" if using
        else "**Channels:** ⚠️ none connected yet — add a channel's secrets (see README) and posting starts automatically.",
    ]
    not_connected = [ALL[c].label for c in s["channels"] if c not in connected]
    if not_connected:
        lines.append(f"<sub>Also a good fit if you connect them: {', '.join(not_connected)}</sub>")
    if s.get("rules"):
        lines += ["", "**Rules from your notes:**", *(f"- {r}" for r in s["rules"])]
    if item.get("watchers"):
        lines += ["", "**Watchers:**"]
        for w in item["watchers"]:
            lines.append(f"- Check **{w['metric']}** every {w['every_hours']:.0f}h on {w['url']}")
            lines += [f"  - 🎉 {describe_trigger(t, w['metric'])}" for t in w["triggers"]]
    if item.get("unsupported"):
        lines += ["", "**⚠️ Notes I won't follow:**", *(f"- {u}" for u in item["unsupported"])]
    if drafts:
        lines += ["", "<details><summary><b>Reddit drafts (post these by hand — check each subreddit's rules first)</b></summary>", ""]
        for d in drafts:
            lines += [f"**{d.get('subreddit', '')}** — {d.get('why', '')}", f"> **{d.get('title', '')}**", ">",
                      *(f"> {l}" for l in str(d.get('body', '')).splitlines()), ""]
        lines.append("</details>")
    lines += [
        "",
        "<sub>Commands (comment on this issue): `pause` · `resume` · `stop` · `status` · `notes: <extra instructions>`. "
        "Edit the issue to change the link or notes. Close it to stop marketing this item.</sub>",
    ]
    return "\n".join(l for l in lines if l is not None)


def intake_from_issue(llm, config: dict, issue: dict, gh=None) -> dict | None:
    form = parse_issue_form(issue.get("body") or "")
    if not form["link"] and not form["manual"]:
        if gh:
            gh.comment(issue["number"], "⚠️ I need a **link** or some **manual details** to market something. Edit the issue to add one.")
        return None
    existing = find_item_by_issue(issue["number"])
    try:
        item = build_item(
            llm, config,
            link=form["link"] or None, notes=form["notes"], manual=form["manual"], image_mode=form["image_mode"],
            source={"type": "link" if form["link"] else "manual", "link": form["link"] or None, "issue": issue["number"]},
            existing=existing,
        )
    except Exception as exc:
        log.exception("intake failed")
        if gh:
            gh.comment(issue["number"], f"❌ I couldn't set this up: `{redact(str(exc))[:500]}`\n\nEdit the issue to try again.")
        if existing:
            existing["status"] = "error"
            save_item(existing)
        return None
    if not existing:
        item["id"] = _unique_id(item["id"])
    save_item(item)
    if gh:
        drafts = reddit_drafts(llm, item) if config["reddit"].get("drafts") and not existing else None
        gh.comment(issue["number"], ("🔄 Updated.\n\n" if existing else "") + summary_markdown(item, config, drafts))
    return item


def add_from_cli(llm, config: dict, link: str | None, notes: str, image_mode: str, manual: str = "") -> dict:
    item = build_item(llm, config, link=link, notes=notes, manual=manual, image_mode=image_mode)
    item["id"] = _unique_id(item["id"])
    save_item(item)
    return item


def update_notes(llm, config: dict, item: dict, extra_notes: str) -> dict:
    notes = (item.get("notes", "") + "\n" + extra_notes).strip()
    updated = build_item(
        llm, config, link=item["source"].get("link"), notes=notes, manual=item.get("manual", ""),
        image_mode=item.get("image_mode", "auto"), source=item["source"], existing=item,
        manual_images=item.get("manual_images", []),
    )
    save_item(updated)
    return updated


def sync_manual_items(llm, config: dict) -> list[str]:
    """Create/refresh items from items/*.yaml (the 'manual way'). Returns changed ids."""
    changed = []
    for path in sorted((ROOT / "items").glob("*.y*ml")):
        raw_text = path.read_text()
        digest = hashlib.sha256(raw_text.encode()).hexdigest()[:16]
        item_id = f"manual-{path.stem}"
        existing = load_item(item_id)
        if existing and existing.get("source", {}).get("hash") == digest:
            continue
        spec = yaml.safe_load(raw_text) or {}
        if spec.get("active") is False:
            if existing and existing["status"] != "paused":
                existing["status"] = "paused"
                save_item(existing)
            continue
        details = {k: v for k, v in spec.items() if k not in ("notes", "image_mode", "images", "link", "active")}
        images = [str(i) for i in spec.get("images") or []]
        try:
            item = build_item(
                llm, config,
                link=spec.get("link"), notes=str(spec.get("notes") or ""),
                manual=yaml.safe_dump(details, allow_unicode=True, sort_keys=False),
                image_mode=str(spec.get("image_mode") or "auto"), manual_images=images,
                source={"type": "manual", "file": f"items/{path.name}", "link": spec.get("link"), "hash": digest},
                existing=existing,
            )
        except Exception as exc:
            log.error("couldn't load %s: %s", path.name, redact(str(exc)))
            continue
        item["id"] = item_id
        item["manual_images"] = images
        if existing is None or item.get("status") != "paused":
            item["status"] = "active"
        save_item(item)
        changed.append(item_id)
    return changed
