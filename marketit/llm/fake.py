"""A deterministic stand-in for a real AI, used by tests and `--fake-ai` dry runs."""

from __future__ import annotations

import json
import re

from ..textutil import parse_number
from .base import LLM


def _between(text: str, start: str, end: str) -> str:
    m = re.search(re.escape(start) + r"(.*?)" + re.escape(end), text, re.S)
    return m.group(1).strip() if m else ""


class FakeLLM(LLM):
    name = "fake"

    def complete(self, prompt, system=None, json_mode=False):
        task = prompt.split("\n", 1)[0].removeprefix("TASK:").strip()
        return json.dumps(getattr(self, f"_{task}", self._unknown)(prompt))

    def _unknown(self, prompt):
        return {}

    def _profile(self, prompt):
        link = _between(prompt, "Link: ", "\n")
        link = None if link.startswith("(") else link
        page_raw = _between(prompt, "<page_content>", "</page_content>")
        try:
            page = json.loads(page_raw) or {}
        except json.JSONDecodeError:
            page = {}
        manual = _between(prompt, "<manual>", "</manual>")
        notes = _between(prompt, "<notes>", "</notes>")
        title = page.get("title") or (manual.splitlines()[0].split(":", 1)[-1].strip() if manual else "Thing")
        kind = "lego_ideas_project" if link and "ideas.lego.com" in link else "physical_product"
        watchers = []
        m = re.search(r"(\d[\d.,]*\s?[km]?)\s+(supporters|backers|downloads|stars|followers)", notes, re.I)
        if m:
            watchers.append({
                "url": link, "metric": m.group(2).lower(), "every_hours": 24,
                "triggers": [{"op": ">=", "value": parse_number(m.group(1)), "message": "celebrate"}],
            })
        rules = [l.strip("- ").strip() for l in notes.splitlines() if l.strip() and "(no notes)" not in l and not m]
        return {
            "kind": kind,
            "title": title,
            "summary": page.get("description") or f"{title}, worth a look.",
            "facts": [page.get("description")] if page.get("description") else [],
            "benefits": ["it's great"],
            "audience": "people who would love it",
            "tone": "friendly",
            "hashtags": ["MarketIt", "NewThing"],
            "price": page.get("price"),
            "link": link,
            "channels": ["bluesky", "mastodon", "pinterest", "telegram", "discord"],
            "posts_per_week": 3,
            "rules": rules,
            "end_date": None,
            "watchers": watchers,
            "unsupported": [],
        }

    def _post(self, prompt):
        title = re.search(r'"title": "([^"]*)"', prompt)
        title = title.group(1) if title else "this"
        link = re.search(r"Include this link exactly once: (\S+)", prompt)
        style = re.search(r"Style for this post: (\w+)", prompt)
        if "MILESTONE" in prompt:
            label = re.search(r'"label": "([^"]*)"', prompt)
            text = f"We did it — {label.group(1) if label else 'a milestone'} Thank you all! {title}"
        else:
            text = f"[{style.group(1) if style else 'post'}] Check out {title}! #MarketIt"
        if link:
            text += f" {link.group(1)}"
        return {"text": text, "title": title, "alt_text": f"Photo of {title}",
                "image_headline": title, "image_prompt": f"a scene featuring {title}"}

    def _shorten(self, prompt):
        body = prompt.split("\n\n", 1)[-1]
        limit = int(re.search(r"at most (\d+)", prompt).group(1))
        return {"text": body[: max(10, limit - 30)]}

    def _metric(self, prompt):
        return {"value": None}

    def _reddit(self, prompt):
        return {"drafts": [{"subreddit": "r/test", "title": "I made a thing", "body": "Feedback welcome!", "why": "fits"}]}
