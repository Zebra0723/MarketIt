"""Decide which channels post now, and which item each one promotes."""

from __future__ import annotations

from datetime import timedelta

from .storage import iso, now, parse_iso

CRON_SLACK_HOURS = 1.5  # the scheduler runs every few hours, so allow some slack


def channel_slot(state: dict, channel: str) -> dict:
    slot = state["channels"].setdefault(channel, {"day": None, "count": 0, "next_at": None})
    today = now().date().isoformat()
    if slot["day"] != today:
        slot.update(day=today, count=0)
    return slot


def channel_due(state: dict, channel: str, cap: int) -> bool:
    slot = channel_slot(state, channel)
    if slot["count"] >= cap:
        return False
    next_at = parse_iso(slot.get("next_at"))
    return next_at is None or now() >= next_at


def mark_channel_used(state: dict, channel: str, cap: int) -> None:
    slot = channel_slot(state, channel)
    slot["count"] += 1
    interval = 24 / max(1, cap)
    earliest = now() + timedelta(hours=max(1.0, interval - CRON_SLACK_HOURS))
    best = state.get("best_hours", {}).get(channel) or []
    if best:
        # Snap to the next learned best hour at or after `earliest` (within a day).
        candidates = []
        for h in best:
            t = earliest.replace(hour=h, minute=0, second=0, microsecond=0)
            if t < earliest:
                t += timedelta(days=1)
            candidates.append(t)
        target = min(candidates)
        if target - earliest <= timedelta(hours=interval):
            earliest = target
    slot["next_at"] = iso(earliest)


def item_channels(item: dict, connected: list[str]) -> list[str]:
    wanted = [c for c in item.get("strategy", {}).get("channels", []) if c in connected]
    return wanted or list(connected)


def is_active(item: dict) -> bool:
    if item.get("status") != "active":
        return False
    end = item.get("strategy", {}).get("end_date")
    if end and now().date().isoformat() > str(end):
        return False
    return True


def pick_item(items: list[dict], channel: str, connected: list[str], recent_posts: list[dict],
              min_hours: float) -> dict | None:
    """Fair rotation: the eligible item that has waited longest on this channel."""
    week_ago = now() - timedelta(days=7)
    candidates = []
    for item in items:
        if not is_active(item) or channel not in item_channels(item, connected):
            continue
        last = parse_iso(item.get("last_posted", {}).get(channel))
        if last and now() - last < timedelta(hours=min_hours):
            continue
        this_week = sum(
            1 for p in recent_posts
            if p["item_id"] == item["id"] and p["channel"] == channel and p.get("kind") == "regular"
            and p.get("status") != "rejected" and parse_iso(p["created_at"]) >= week_ago
        )
        if this_week >= item["strategy"].get("posts_per_week", 3):
            continue
        candidates.append((last.timestamp() if last else 0, item.get("post_count", 0), item["id"], item))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[:3])
    return candidates[0][3]
