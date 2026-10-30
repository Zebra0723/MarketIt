"""The scheduled run, in two stages so images are pushed before platforms fetch them:

  prepare: refresh items, check milestones, write posts + ads into data/queue/
  (workflow commits and pushes)
  publish: post everything that's ready, ask for approvals, collect stats
"""

from __future__ import annotations

import logging
import random
from datetime import timedelta

from .approvals import needs_approval, approvals_remaining, request_pending_approvals
from .config import env, redact
from .generate import write_post
from .github import GitHub
from .images import prepare_post_images, prune_media
from .intake import sync_manual_items
from .learning import engagement, recompute_scores
from .llm import get_llm
from .planner import channel_due, is_active, item_channels, mark_channel_used, pick_item
from .publishers import ALL, PublishError, connected_channels, get_publisher
from .storage import (all_items, archive_post, data_dir, history_posts, iso, load_state, now, parse_iso,
                      queued_posts, save_history_post, save_item, save_queued, save_state)
from .watchers import check_item_watchers

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


def _all_posts() -> list[dict]:
    return history_posts() + queued_posts()


def _queue_post(item, post, publisher, status):
    post["image"], post["extra_images"] = prepare_post_images(item, post, publisher)
    post["status"] = status
    save_queued(post)
    item["last_posted"][publisher.name] = iso()
    item["post_count"] = item.get("post_count", 0) + 1
    return post


def prepare(config: dict, llm=None, rng: random.Random | None = None) -> dict:
    rng = rng or random.Random()
    llm = llm or get_llm(config)
    state = load_state()
    summary = {"milestones": 0, "queued": 0, "errors": []}

    sync_manual_items(llm, config)
    connected = connected_channels(config)
    items = all_items()

    for item in items:
        if item.get("status") == "active" and not is_active(item):
            item["status"] = "ended"
            save_item(item)

    # 1. Watchers -> milestone posts (always automatic; not limited by daily caps).
    page_cache: dict = {}
    for item in items:
        if not is_active(item) or not item.get("watchers"):
            continue
        events = check_item_watchers(llm, item, page_cache)
        for event in events:
            if event["metric"] == "days left" and (item.get("project") or {}).get("supporters", 0) and \
                    item["project"]["supporters"] >= 10000:
                continue  # already in LEGO review; the deadline no longer matters
            for channel in item_channels(item, connected):
                publisher = get_publisher(channel, config)
                try:
                    post = write_post(llm, item, publisher, state, config, _all_posts(), rng, kind="milestone", milestone=event)
                    post["milestone"] = event
                    _queue_post(item, post, publisher, "ready")
                    summary["milestones"] += 1
                except Exception as exc:
                    summary["errors"].append(f"{item['id']}/{channel} milestone: {redact(str(exc))}")
        save_item(item)

    # 2. Regular posts, within each channel's daily cap.
    gated = needs_approval(state, config)
    slots_left = None
    if gated:
        waiting = sum(1 for p in queued_posts() if p["status"] == "awaiting_approval")
        slots_left = max(0, approvals_remaining(state, config) - waiting)

    for channel in connected:
        if slots_left is not None and slots_left <= 0:
            break
        cap = int((config["channels"].get(channel) or {}).get("daily_cap", 2))
        if not channel_due(state, channel, cap):
            continue
        posts = _all_posts()
        item = pick_item(items, channel, connected, posts, config["posting"]["min_hours_between_same_item"])
        if not item:
            continue
        publisher = get_publisher(channel, config)
        try:
            post = write_post(llm, item, publisher, state, config, posts, rng)
            _queue_post(item, post, publisher, "awaiting_approval" if gated else "ready")
            save_item(item)
            mark_channel_used(state, channel, cap)
            summary["queued"] += 1
            if slots_left is not None:
                slots_left -= 1
        except Exception as exc:
            log.exception("post generation failed")
            summary["errors"].append(f"{item['id']}/{channel}: {redact(str(exc))}")

    prune_media(int(config["media"].get("keep_days", 45)))
    save_state(state)
    return summary


def public_image_url(config: dict, rel_path: str | None, gh=None) -> str | None:
    if not rel_path:
        return None
    base = config["media"].get("public_base_url")
    if base:
        return f"{base.rstrip('/')}/{rel_path.split('/', 1)[-1]}"
    repo = env("GITHUB_REPOSITORY")
    public = env("MARKETIT_REPO_PUBLIC") == "true" or (gh is not None and gh.repo_is_public())
    if repo and public:
        branch = env("GITHUB_REF_NAME") or "main"
        return f"https://raw.githubusercontent.com/{repo}/{branch}/data/{rel_path}"
    return None


def publish_queue(config: dict, gh=None, dry_run: bool = False) -> dict:
    gh = gh if gh is not None else GitHub.from_env()
    connected = set(connected_channels(config))
    items = {i["id"]: i for i in all_items()}
    result = {"published": [], "failed": [], "dry_run": []}

    ready = [p for p in queued_posts() if p["status"] == "ready"]
    ready.sort(key=lambda p: (p["kind"] != "milestone", p["created_at"]))
    for post in ready:
        if dry_run:
            result["dry_run"].append(post)
            continue
        item = items.get(post["item_id"])
        if post["channel"] not in connected:
            post.update(status="failed", last_error="channel is no longer connected")
            archive_post(post)
            result["failed"].append(post)
            continue
        publisher = get_publisher(post["channel"], config)
        image_path = data_dir() / post["image"] if post.get("image") else None
        extra_paths = [data_dir() / p for p in post.get("extra_images") or [] if (data_dir() / p).exists()]
        image_url = public_image_url(config, post.get("image"), gh) if publisher.needs_public_image_url else None
        if publisher.needs_public_image_url and post.get("image") and not image_url:
            if publisher.image_required:
                post.update(status="failed", last_error=f"{publisher.label} needs a public image URL — set media.public_base_url")
                archive_post(post)
                result["failed"].append(post)
                continue
            image_path, extra_paths = None, []  # e.g. Threads: fall back to a text post
        try:
            res = publisher.publish(post, image_path, image_url, extra_paths)
        except Exception as exc:
            post["attempts"] = post.get("attempts", 0) + 1
            post["last_error"] = redact(str(exc))[:500]
            permanent = isinstance(exc, PublishError) and exc.permanent
            if permanent or post["attempts"] >= MAX_ATTEMPTS:
                post["status"] = "failed"
                archive_post(post)
                result["failed"].append(post)
                issue = (item or {}).get("source", {}).get("issue")
                if gh and issue:
                    gh.comment(issue, f"❌ Couldn't post to {publisher.label} (`{post['id']}`): `{post['last_error'][:300]}`")
            else:
                save_queued(post)
            continue
        post.update(status="published", published_at=iso(), platform_id=res.get("id"), url=res.get("url"))
        archive_post(post)
        result["published"].append(post)
        issue = (item or {}).get("source", {}).get("issue")
        if gh and issue and post["kind"] == "milestone":
            gh.comment(issue, f"🎉 Milestone posted on {publisher.label}: **{post.get('milestone_label')}** {post.get('url') or ''}")

    if not dry_run:
        state = load_state()
        request_pending_approvals(gh, state, config, items)
        save_state(state)
    return result


def collect_stats(config: dict, force: bool = False) -> int:
    state = load_state()
    last = parse_iso(state.get("last_stats_at"))
    if not force and last and now() - last < timedelta(hours=config["posting"]["stats_every_hours"]):
        return 0
    cutoff = now() - timedelta(days=30)
    updated = 0
    posts = history_posts()
    for post in posts:
        if post.get("status") != "published" or parse_iso(post["published_at"]) < cutoff:
            continue
        publisher_cls = ALL.get(post["channel"])
        if not publisher_cls or not publisher_cls.configured():
            continue
        try:
            metrics = get_publisher(post["channel"], config).fetch_metrics(post)
        except Exception as exc:
            log.info("metrics for %s failed: %s", post["id"], redact(str(exc)))
            continue
        if metrics is None:
            continue
        post["metrics"] = metrics
        post["engagement"] = engagement(metrics)
        post["metrics_at"] = iso()
        save_history_post(post)
        updated += 1
    recompute_scores(state, posts)
    state["last_stats_at"] = iso()
    save_state(state)
    return updated
