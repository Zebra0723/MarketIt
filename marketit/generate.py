"""Write a platform-shaped post for an item."""

from __future__ import annotations

import logging
import random

from . import prompts
from .learning import choose_style
from .llm import LLMError, ask_json
from .storage import iso
from .textutil import fit_text, new_post_id

log = logging.getLogger(__name__)


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
    written_by = "ai"
    try:
        reply = ask_json(
            llm,
            prompts.post_prompt(item, publisher, style, recent_texts(item["id"], posts), kind, milestone),
            system=prompts.SYSTEM,
        )
    except LLMError as exc:
        log.warning("AI unavailable (%s); writing the post from a template", str(exc)[:200])
        reply, written_by = template_post(item, publisher, style, kind, milestone, rng), "template"
    link = item["profile"].get("link")
    text = str(reply.get("text", "")).strip()
    if not text:
        raise ValueError("the AI returned an empty post")
    if len(text) > publisher.max_chars and written_by == "ai":
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
        "image_headline": str(reply.get("image_headline") or item["profile"]["title"])[:80],
        "milestone_label": milestone["label"] if milestone else None,
        "milestone": milestone,
        "image": None,
        "extra_images": [],
        "status": "draft",
        "created_at": iso(),
        "attempts": 0,
        "written_by": written_by,
    }


HOOKS = {
    "feature_spotlight": ["Take a closer look at {title} 👀", "One of my favourite details in {title}:"],
    "behind_the_build": ["The story behind {title} 🧱", "How {title} came together:"],
    "progress_push": ["{title} is at {supporters} supporters! 🚀", "Every vote counts for {title}!"],
    "why_it_should_be_a_set": ["Why {title} deserves to be a real LEGO set:", "Imagine {title} on store shelves 🧱"],
    "imagine": ["Imagine building {title} 🧱", "Picture {title} on your shelf ✨"],
    "question": ["Would you build {title}? 🤔", "Which detail of {title} do you like most?"],
    "how_to_support": ["Supporting {title} on LEGO Ideas is free and takes a minute 💡",
                       "Want {title} to become a real set? Here's how to help:"],
}


def template_post(item: dict, publisher, style: str | None, kind: str, milestone: dict | None,
                  rng: random.Random) -> dict:
    """A decent post built from the project profile, for when no AI is available."""
    p, stats = item["profile"], item.get("project") or {}
    title = p.get("title") or "this LEGO Ideas project"
    supporters = stats.get("supporters")
    sup = f"{supporters:,}" if supporters is not None else "growing"
    goal = stats.get("next_goal")
    tags = " ".join(f"#{h}" for h in (p.get("hashtags") or ["LEGOIdeas", "LEGO"])[:3])
    if kind == "milestone" and milestone and milestone.get("metric") == "days left":
        text = (f"⏳ Only {int(milestone['value'])} days left for {title} on LEGO Ideas! "
                f"It has {sup} supporters — help it reach {goal:,} before time runs out." if goal else "")
        headline = "Time is running out"
    elif kind == "milestone" and milestone:
        text = (f"🎉 {title} just reached {int(milestone['threshold']):,} supporters on LEGO Ideas! "
                f"Thank you all!" + (f" Next goal: {goal:,}." if goal else ""))
        headline = "Thank you, supporters!"
    else:
        hook = rng.choice(HOOKS.get(style or "", HOOKS["progress_push"])).format(title=title, supporters=sup)
        detail = (p.get("facts") or p.get("selling_points") or [p.get("summary", "")])[0]
        progress = f"{sup} supporters so far" + (f", next goal {goal:,}" if goal and supporters is not None else "")
        text = f"{hook}\n\n{detail}\n\n{progress}. Support it for free on LEGO Ideas 👇"
        headline = (p.get("selling_points") or [title])[0]
    text = f"{text}\n\n{tags}" if publisher.hashtags != "no hashtags" else text
    return {"text": text, "title": title, "alt_text": f"Photo of the LEGO Ideas project {title}",
            "image_headline": headline}
