"""Write a platform-shaped post for an item."""

from __future__ import annotations

import random

from . import prompts
from .learning import choose_style
from .llm import ask_json
from .storage import iso
from .textutil import fit_text, new_post_id


def recent_texts(item_id: str, posts: list[dict], n: int = 5) -> list[str]:
    mine = [p for p in posts if p["item_id"] == item_id and p.get("text")]
    return [p["text"] for p in mine[-n:]]


def last_style(item_id: str, posts: list[dict]) -> str | None:
    for p in reversed(posts):
        if p["item_id"] == item_id and p.get("style"):
            return p["style"]
    return None


def write_post(llm, item: dict, publisher, state: dict, config: dict, posts: list[dict],
               rng: random.Random, kind: str = "regular", milestone: dict | None = None) -> dict:
    style = None
    if kind == "regular":
        style = choose_style(state, publisher.name, rng, config["posting"]["explore_rate"],
                             avoid=last_style(item["id"], posts))
    reply = ask_json(
        llm,
        prompts.post_prompt(item, publisher, style, recent_texts(item["id"], posts), kind, milestone),
        system=prompts.SYSTEM,
    )
    link = item["profile"].get("link")
    text = str(reply.get("text", "")).strip()
    if not text:
        raise ValueError("the AI returned an empty post")
    if len(text) > publisher.max_chars:
        try:
            shorter = ask_json(llm, prompts.shorten_prompt(text, publisher.max_chars, link), system=prompts.SYSTEM)
            text = str(shorter.get("text") or text).strip()
        except Exception:
            pass
    text = fit_text(text, publisher.max_chars, link)

    return {
        "id": new_post_id(),
        "item_id": item["id"],
        "channel": publisher.name,
        "kind": kind,
        "style": style,
        "text": text,
        "title": str(reply.get("title") or item["profile"]["title"])[:100],
        "alt_text": str(reply.get("alt_text") or item["profile"]["title"])[:1000],
        "link": link,
        "image_prompt": reply.get("image_prompt"),
        "image_headline": str(reply.get("image_headline") or item["profile"]["title"])[:80],
        "milestone_label": milestone["label"] if milestone else None,
        "image": None,
        "status": "draft",
        "created_at": iso(),
        "attempts": 0,
    }
