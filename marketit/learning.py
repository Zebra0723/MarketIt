"""Learn which post styles and posting hours work best on each channel."""

from __future__ import annotations

import random
import statistics
from collections import defaultdict
from datetime import timedelta

from .prompts import STYLES
from .storage import now, parse_iso

MIN_SAMPLES = 3


def engagement(metrics: dict) -> float:
    return (
        metrics.get("likes", 0)
        + 2 * metrics.get("reposts", 0)
        + 3 * metrics.get("replies", 0)
        + metrics.get("clicks", 0)
    )


def recompute_scores(state: dict, posts: list[dict]) -> None:
    """Score styles and hours from published posts that have had a day to collect engagement."""
    mature = [
        p for p in posts
        if p.get("status") == "published" and p.get("metrics") and p.get("kind") == "regular"
        and parse_iso(p["published_at"]) <= now() - timedelta(hours=24)
    ]
    by_channel = defaultdict(list)
    for p in mature:
        by_channel[p["channel"]].append(p)

    style_scores, best_hours = {}, {}
    for channel, plist in by_channel.items():
        median = statistics.median(engagement(p["metrics"]) for p in plist)
        styles, hours = defaultdict(list), defaultdict(list)
        for p in plist:
            norm = engagement(p["metrics"]) / (median + 1)
            if p.get("style"):
                styles[p["style"]].append(norm)
            hours[parse_iso(p["published_at"]).hour].append(norm)
        style_scores[channel] = {s: {"n": len(v), "mean": round(sum(v) / len(v), 3)} for s, v in styles.items()}
        ranked = sorted(
            ((sum(v) / len(v), h) for h, v in hours.items() if len(v) >= MIN_SAMPLES), reverse=True
        )
        best_hours[channel] = [h for _, h in ranked[:3]]
    state["style_scores"] = style_scores
    state["best_hours"] = best_hours


def choose_style(state: dict, channel: str, rng: random.Random, explore_rate: float,
                 avoid: str | None = None) -> str:
    scores = state.get("style_scores", {}).get(channel, {})
    proven = {s: v for s, v in scores.items() if v["n"] >= MIN_SAMPLES and s in STYLES and s != avoid}
    options = [s for s in STYLES if s != avoid]
    if not proven or rng.random() < explore_rate:
        # Explore: favour styles we know least about.
        fewest = min(scores.get(s, {}).get("n", 0) for s in options)
        return rng.choice([s for s in options if scores.get(s, {}).get("n", 0) == fewest])
    return max(proven, key=lambda s: proven[s]["mean"])
