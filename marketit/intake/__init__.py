"""Adding LEGO Ideas projects: from a GitHub issue, from the command line, or from items/*.yaml."""

from __future__ import annotations

import hashlib
import logging

import yaml

from .. import legoideas, prompts
from ..config import ROOT, redact
from ..llm import LLMError, ask_json
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


def summary_markdown(item: dict, config: dict, drafts: list[dict] | None = None) -> str:
    p, s, stats = item["profile"], item["strategy"], item.get("project") or {}
    connected = connected_channels(config)
    using = item_channels(item, connected) if connected else []
    supporters = stats.get("supporters")
    milestones = [int(t["value"]) for w in item.get("watchers", []) if w["metric"] == "supporters" for t in w["triggers"]]
    upcoming = [m for m in milestones if supporters is None or m > supporters]
    alerts = [int(t["value"]) for w in item.get("watchers", []) if w["metric"] == "days left" for t in w["triggers"]]
    photos = len(p.get("images", []))
    lines = [
        f"## ✅ Got it: **{p['title']}**" + (f" by {stats['creator']}" if stats.get("creator") else ""),
        "",
        f"{p['summary']}",
        "",
        f"**Supporters:** {supporters:,}" if supporters is not None else "**Supporters:** couldn't read yet (will retry)",
        f"**Days left:** {stats['days_left']}" if stats.get("days_left") is not None else "",
        f"**Audience:** {p['audience']}",
        f"**Photos from the project page:** {photos}" if photos
        else "**Photos:** ⚠️ none found on the page — I won't post until I can read the project's photos.",
        "",
        f"**Milestone posts at:** {', '.join(f'{m:,}' for m in upcoming[:12])} supporters" if upcoming else "",
        f"**Countdown posts at:** {', '.join(str(a) for a in alerts)} days left" if alerts else "",
        f"**Regular posts:** about {s['posts_per_week']} per week per channel"
        + (f", until {s['end_date']}" if s.get("end_date") else ""),
        f"**Channels:** {', '.join(ALL[c].label for c in using)}" if using
        else "**Channels:** ⚠️ none connected yet — add a channel's secrets (see README) and posting starts automatically.",
    ]
    not_connected = [ALL[c].label for c in s["channels"] if c not in connected]
    if not_connected:
        lines.append(f"<sub>Also a good fit if you connect them: {', '.join(not_connected)}</sub>")
    if s.get("rules"):
        lines += ["", "**Rules from your notes:**", *(f"- {r}" for r in s["rules"])]
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
        "<sub>Commands (comment on this issue): `pause` · `resume` · `stop` · `status` · `refresh` · `notes: <extra instructions>`. "
        "Edit the issue to change the link or notes. Close it to stop.</sub>",
    ]
    return "\n".join(l for l in lines if l is not None)


NOT_LEGO = ("⚠️ MarketIt works with **LEGO Ideas project links**, like `https://ideas.lego.com/product-ideas/…`. "
            "Edit the issue to paste one.")


def intake_from_issue(llm, config: dict, issue: dict, gh=None) -> dict | None:
    form = parse_issue_form(issue.get("body") or "")
    if not legoideas.is_project_url(form["link"]):
        if gh:
            gh.comment(issue["number"], NOT_LEGO)
        return None
    existing = find_item_by_issue(issue["number"])
    try:
        item = build_item(
            llm, config, link=form["link"], notes=form["notes"],
            source={"type": "link", "link": legoideas.canonical_url(form["link"]), "issue": issue["number"]},
            existing=existing,
        )
    except LLMError:
        raise  # an AI provider problem, not a problem with the issue: the caller retries later
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


def add_from_cli(llm, config: dict, link: str, notes: str) -> dict:
    item = build_item(llm, config, link=link, notes=notes)
    item["id"] = _unique_id(item["id"])
    save_item(item)
    return item


def update_notes(llm, config: dict, item: dict, extra_notes: str) -> dict:
    notes = (item.get("notes", "") + "\n" + extra_notes).strip()
    updated = build_item(llm, config, link=item["profile"]["link"], notes=notes, source=item["source"], existing=item)
    save_item(updated)
    return updated


def sync_manual_items(llm, config: dict) -> list[str]:
    """Create/refresh projects listed as items/*.yaml files (link + optional notes). Returns changed ids."""
    changed = []
    for path in sorted((ROOT / "items").glob("*.y*ml")):
        raw_text = path.read_text()
        digest = hashlib.sha256(raw_text.encode()).hexdigest()[:16]
        item_id = f"file-{path.stem}"
        existing = load_item(item_id)
        if existing and existing.get("source", {}).get("hash") == digest:
            continue
        spec = yaml.safe_load(raw_text) or {}
        if spec.get("active") is False:
            if existing and existing["status"] != "paused":
                existing["status"] = "paused"
                save_item(existing)
            continue
        try:
            item = build_item(
                llm, config, link=str(spec.get("link") or ""), notes=str(spec.get("notes") or ""),
                source={"type": "file", "file": f"items/{path.name}", "link": spec.get("link"), "hash": digest},
                existing=existing,
            )
        except Exception as exc:
            log.error("couldn't load %s: %s", path.name, redact(str(exc)))
            continue
        item["id"] = item_id
        item["status"] = "active"
        save_item(item)
        changed.append(item_id)
    return changed
