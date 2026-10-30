"""Watchers: check a number on a page on a schedule and fire milestone posts.

Each one-off trigger fires exactly once. Thresholds already passed when a watcher is
first created are marked as passed without posting, and a sudden implausible jump
or drop is held back until the next check confirms it.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import timedelta

from . import prompts
from .intake.fetch import fetch_page
from .llm import ask_json
from .storage import iso, now, parse_iso
from .textutil import format_number, parse_number

log = logging.getLogger(__name__)
NUM = r"(\d[\d.,]*\s?[kKmM]?)(?![\d])"
MAX_HISTORY = 500


def _metric_words(metric: str) -> list[str]:
    m = metric.lower().strip()
    words = [m]
    if m.endswith("s"):
        words.append(m[:-1])
    first = m.split()[0] if m.split() else m
    if first not in words:
        words.append(first)
    return words


def extract_metric_regex(text: str, metric: str) -> float | None:
    low = text.lower()
    for word in _metric_words(metric):
        w = re.escape(word)
        for pattern in (NUM + r"[^\d]{0,25}?\b" + w + r"\b", r"\b" + w + r"\b[^\d]{0,25}?" + NUM):
            m = re.search(pattern, low)
            if m:
                value = parse_number(m.group(1))
                if value is not None:
                    return value
    return None


def read_metric(llm, url: str, metric: str, page_cache: dict) -> float:
    from . import legoideas

    if url not in page_cache:
        page_cache[url] = fetch_page(url)
    page = page_cache[url]
    if legoideas.is_project_url(url) and metric.lower() in ("supporters", "days left"):
        key = ("stats", url)
        if key not in page_cache:
            page_cache[key] = legoideas.read_stats(page, llm)
        value = page_cache[key]["supporters" if metric.lower() == "supporters" else "days_left"]
        if value is None:
            raise ValueError(f'couldn\'t find "{metric}" on {url}')
        return float(value)
    value = extract_metric_regex(page.text, metric)
    if value is None and llm is not None:
        reply = ask_json(llm, prompts.metric_prompt(metric, page.text))
        raw = reply.get("value") if isinstance(reply, dict) else None
        value = float(raw) if isinstance(raw, (int, float)) else parse_number(str(raw)) if raw else None
    if value is None:
        raise ValueError(f'couldn\'t find "{metric}" on {url}')
    return value


def is_due(watcher: dict) -> bool:
    last = parse_iso(watcher.get("last_checked"))
    if not last:
        return True
    return now() - last >= timedelta(hours=watcher["every_hours"] * 0.9)


def _suspicious(prev: float | None, value: float, metric: str) -> bool:
    if prev is None or prev < 20 or "day" in metric.lower():
        return False  # countdowns legitimately drop, and jump when a project earns extra time
    return value < prev * 0.5 or value > prev * 20


def _label(op: str, value: float, threshold: float, metric: str, increase: float | None = None, window=None) -> str:
    if op == "increase":
        return f"+{format_number(increase)} {metric} in {int(window)}h"
    if op == "<=":
        return f"{format_number(value)} {metric}"
    return f"{format_number(threshold)} {metric}!"


def evaluate(watcher: dict, value: float) -> list[dict]:
    """Record a new reading and return the triggers it fires."""
    history = watcher.setdefault("history", [])
    fired = watcher.setdefault("fired", [])
    first_reading = not history
    prev = history[-1]["v"] if history else None
    t_now = iso()

    if _suspicious(prev, value, watcher.get("metric", "")):
        suspect = watcher.get("suspect")
        if not suspect or abs(suspect - value) > max(1, value * 0.1):
            watcher["suspect"] = value
            log.info("watcher %s: holding back suspicious reading %s (was %s)", watcher["id"], value, prev)
            return []
    watcher.pop("suspect", None)

    history.append({"t": t_now, "v": value})
    del history[:-MAX_HISTORY]
    fired_ids = {f["trigger_id"] for f in fired}
    events = []

    for trig in watcher.get("triggers", []):
        op, threshold = trig["op"], trig["value"]
        hit = None
        if op in (">=", "<="):
            if trig["id"] in fired_ids:
                continue
            reached = value >= threshold if op == ">=" else value <= threshold
            if reached:
                fired.append({"trigger_id": trig["id"], "at": t_now, "value": value, "silent": first_reading})
                if not first_reading:
                    hit = threshold
        elif op == "every":
            multiple = math.floor(value / threshold)
            last = trig.get("last_multiple")
            if last is None or first_reading:
                trig["last_multiple"] = multiple
            elif multiple > last:
                trig["last_multiple"] = multiple
                hit = multiple * threshold
                fired.append({"trigger_id": trig["id"], "at": t_now, "value": value, "threshold": hit})
        elif op == "increase":
            window = trig.get("window_hours", 24)
            start = now() - timedelta(hours=window)
            last_fire = max((parse_iso(f["at"]) for f in fired if f["trigger_id"] == trig["id"]), default=None)
            if last_fire and now() - last_fire < timedelta(hours=window):
                continue
            base_points = [h["v"] for h in history[:-1] if parse_iso(h["t"]) >= start]
            if not base_points and len(history) > 1:
                base_points = [history[-2]["v"]]
            if base_points and value - min(base_points) >= threshold:
                hit = threshold
                trig["_increase"] = value - min(base_points)
                fired.append({"trigger_id": trig["id"], "at": t_now, "value": value})
        if hit is not None:
            events.append({
                "watcher_id": watcher["id"],
                "trigger_id": trig["id"],
                "metric": watcher["metric"],
                "value": value,
                "threshold": hit,
                "label": _label(op, value, hit, watcher["metric"], trig.pop("_increase", None), trig.get("window_hours")),
                "message": trig.get("message", ""),
            })
    return _most_relevant(events, watcher)


def _most_relevant(events: list[dict], watcher: dict) -> list[dict]:
    """If one reading passes several thresholds at once (e.g. 240 -> 510 passes 250 and 500),
    post only about the most significant one; the others still count as fired."""
    ops = {t["id"]: t["op"] for t in watcher.get("triggers", [])}
    best: dict[str, dict] = {}
    for e in events:
        op = ops[e["trigger_id"]]
        cur = best.get(op)
        if cur is None or (e["threshold"] < cur["threshold"] if op == "<=" else e["threshold"] > cur["threshold"]):
            best[op] = e
    return [e for e in events if best.get(ops[e["trigger_id"]]) is e]


def check_item_watchers(llm, item: dict, page_cache: dict | None = None) -> list[dict]:
    """Check every due watcher on an item. Returns milestone events (with item_id)."""
    page_cache = {} if page_cache is None else page_cache
    events = []
    refreshed = False
    for watcher in item.get("watchers", []):
        if not is_due(watcher):
            continue
        refreshed = True
        watcher["last_checked"] = iso()
        try:
            value = read_metric(llm, watcher["url"], watcher["metric"], page_cache)
        except Exception as exc:
            watcher["last_error"] = str(exc)[:300]
            log.warning("watcher %s on %s failed: %s", watcher["id"], item["id"], exc)
            continue
        watcher["last_error"] = None
        for event in evaluate(watcher, value):
            event["item_id"] = item["id"]
            events.append(event)
    if refreshed:
        refresh_project_stats(item, page_cache, llm)
    return events


def refresh_project_stats(item: dict, page_cache: dict, llm=None) -> None:
    """Keep the live numbers shown in posts and ads (supporters, days left) up to date."""
    from . import legoideas
    from .storage import save_page_snapshot

    url = item.get("profile", {}).get("link")
    page = page_cache.get(url)
    if page is None:
        return
    photos = legoideas.project_images(page.images, page.scripts)[:12]
    if photos:
        item["profile"]["images"] = photos   # pick up new or changed project photos
    fresh = page_cache.get(("stats", url)) or legoideas.read_stats(page, llm)
    stats = item.setdefault("project", {})
    for key, value in fresh.items():
        if value is not None:
            stats[key] = value
    save_page_snapshot(url, page, stats)
    stats["next_goal"] = legoideas.next_milestone(stats.get("supporters"))
    stats["updated_at"] = iso()
