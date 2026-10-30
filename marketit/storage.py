"""All state lives as JSON files under data/ so the repo itself is the database."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT


def data_dir() -> Path:
    return Path(os.environ.get("MARKETIT_DATA", ROOT / "data"))


def now() -> datetime:
    override = os.environ.get("MARKETIT_NOW")
    if override:
        return datetime.fromisoformat(override)
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).isoformat(timespec="seconds")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


# Items ---------------------------------------------------------------------

def items_dir() -> Path:
    return data_dir() / "items"


def load_item(item_id: str) -> dict | None:
    return read_json(items_dir() / f"{item_id}.json")


def save_item(item: dict) -> None:
    item["updated_at"] = iso()
    write_json(items_dir() / f"{item['id']}.json", item)


def all_items() -> list[dict]:
    d = items_dir()
    if not d.exists():
        return []
    return [read_json(p) for p in sorted(d.glob("*.json"))]


def find_item_by_issue(issue_number: int) -> dict | None:
    for item in all_items():
        if item.get("source", {}).get("issue") == issue_number:
            return item
    return None


# Queue (posts waiting for approval or publishing) ---------------------------

def queue_dir() -> Path:
    return data_dir() / "queue"


def save_queued(post: dict) -> None:
    write_json(queue_dir() / f"{post['id']}.json", post)


def load_queued(post_id: str) -> dict | None:
    return read_json(queue_dir() / f"{post_id}.json")


def queued_posts() -> list[dict]:
    d = queue_dir()
    if not d.exists():
        return []
    return sorted((read_json(p) for p in d.glob("*.json")), key=lambda p: p["created_at"])


def remove_queued(post_id: str) -> None:
    (queue_dir() / f"{post_id}.json").unlink(missing_ok=True)


# Post history ----------------------------------------------------------------

def history_dir() -> Path:
    return data_dir() / "posts"


def archive_post(post: dict) -> None:
    """Move a finished (published / rejected / failed) post from the queue to history."""
    month = post["created_at"][:7]
    write_json(history_dir() / month / f"{post['id']}.json", post)
    remove_queued(post["id"])


def save_history_post(post: dict) -> None:
    write_json(history_dir() / post["created_at"][:7] / f"{post['id']}.json", post)


def history_posts() -> list[dict]:
    d = history_dir()
    if not d.exists():
        return []
    return sorted((read_json(p) for p in d.glob("*/*.json")), key=lambda p: p["created_at"])


# Global state ------------------------------------------------------------------

def load_state() -> dict:
    state = read_json(data_dir() / "state.json", {}) or {}
    state.setdefault("approved_count", 0)
    state.setdefault("channels", {})
    state.setdefault("style_scores", {})
    state.setdefault("best_hours", {})
    state.setdefault("last_stats_at", None)
    state.setdefault("approvals_issue", None)
    return state


def save_state(state: dict) -> None:
    write_json(data_dir() / "state.json", state)


def media_dir() -> Path:
    return data_dir() / "media"


def save_page_snapshot(url: str, page, stats: dict) -> None:
    """Keep a copy of what MarketIt last read from a project page (for checking and debugging)."""
    import re as _re

    from . import legoideas

    pid = legoideas.project_id(url) or "page"
    hits = []
    for m in _re.finditer(r'(?i)\\?"[A-Za-z_]*(?:support|vote|day|expir|author|creator|user)[A-Za-z_]*\\?"\s*:', page.scripts):
        hits.append(page.scripts[m.start(): m.start() + 120].replace("\n", " "))
        if len(hits) >= 150:
            break
    lines = [
        f"# Snapshot of {url}", f"read at {iso()}", "",
        f"title: {page.title}", f"description: {page.description}", "",
        f"stats used: {stats}", "",
        "## images", *page.images, "",
        "## data keys found in scripts (first 150)", *hits, "",
        "## visible text (first 20,000 characters)", page.text[:20000],
    ]
    out = data_dir() / "pages" / f"{pid}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
