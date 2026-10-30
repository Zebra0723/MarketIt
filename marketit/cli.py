"""Command line: python -m marketit <command>"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .config import load_config, redact
from .llm import get_llm

log = logging.getLogger("marketit")


def _llm(args, config):
    return get_llm(config, force="fake" if getattr(args, "fake_ai", False) else None)


def cmd_add(args, config):
    from .intake import add_from_cli, summary_markdown

    item = add_from_cli(_llm(args, config), config, args.link, args.notes or "")
    print(summary_markdown(item, config))
    print(f"\nSaved as item '{item['id']}'. Try: python -m marketit preview {item['id']}")


def cmd_sync(args, config):
    """Process new/edited/closed item issues and comment commands from GitHub."""
    from .github import GitHub
    from .sync import sync

    gh = GitHub.from_env()
    if gh is None:
        print("GITHUB_TOKEN / GITHUB_REPOSITORY not set; nothing to sync")
        return
    print(json.dumps(sync(config, lambda: _llm(args, config), gh)))


def cmd_prepare(args, config):
    from .llm import LLMError
    from .runner import prepare

    try:
        llm = _llm(args, config)
    except LLMError as exc:
        print(f"⏸️  Skipping: {exc}")
        return
    summary = prepare(config, llm)
    print(json.dumps(summary, indent=2))


def _print_publish(result):
    for p in result["published"]:
        print(f"✅ {p['channel']}: {p.get('url') or p['id']}")
    for p in result["failed"]:
        print(f"❌ {p['channel']} {p['id']}: {p.get('last_error')}")
    for p in result["dry_run"]:
        print(f"--- [dry run] {p['channel']} ({p['kind']}, {p.get('style')}) image={p.get('image')}\n{p['text']}\n")


def cmd_publish(args, config):
    from .runner import collect_stats, publish_queue

    result = publish_queue(config, dry_run=args.dry_run)
    _print_publish(result)
    if not args.dry_run:
        n = collect_stats(config)
        if n:
            print(f"📈 updated stats for {n} posts")


def cmd_run(args, config):
    """prepare + publish in one go (for running on your own computer)."""
    cmd_prepare(args, config)
    cmd_publish(args, config)


def cmd_preview(args, config):
    """Write sample posts for an item on every channel that suits it, without saving or posting."""
    import random

    from .generate import write_post
    from .images import prepare_post_images
    from .publishers import ALL, get_publisher
    from .storage import all_items, history_posts, load_item, load_state

    items = [load_item(args.item_id)] if args.item_id else all_items()
    items = [i for i in items if i]
    if not items:
        sys.exit("no items yet — add one first")
    llm, state, rng = _llm(args, config), load_state(), random.Random()
    for item in items:
        for channel in item["strategy"]["channels"]:
            publisher = get_publisher(channel, config)
            post = write_post(llm, item, publisher, state, config, history_posts(), rng)
            post["id"] = f"preview-{item['id']}-{channel}"
            image, extras = prepare_post_images(item, post, publisher)
            print(f"=== {ALL[channel].label} · {item['profile']['title']} · {post['template']} ad · angle {post['style']}")
            print(post["text"])
            print(f"[ad: data/{image}]  [+{len(extras)} project photos]\n")


def cmd_stats(args, config):
    from .runner import collect_stats
    from .storage import load_state

    n = collect_stats(config, force=True)
    state = load_state()
    print(f"updated {n} posts")
    print(json.dumps({"style_scores": state["style_scores"], "best_hours": state["best_hours"]}, indent=2))


def cmd_approve(args, config):
    from .approvals import approve, reject
    from .storage import load_queued, load_state, save_state

    state = load_state()
    post = load_queued(args.post_id.upper())
    if not post or post["status"] != "awaiting_approval":
        sys.exit(f"{args.post_id} isn't waiting for approval")
    if args.reject:
        reject(post)
        print("rejected")
    else:
        approve(post, state, args.text)
        print("approved — it will be posted on the next publish")
    save_state(state)


def cmd_status(args, config):
    from .approvals import approvals_remaining
    from .publishers import ALL, connected_channels
    from .storage import all_items, load_state, queued_posts

    state = load_state()
    connected = connected_channels(config)
    print("Channels connected:", ", ".join(connected) or "none")
    print("Not connected:", ", ".join(c for c in ALL if c not in connected))
    print(f"Approvals left before full auto: {approvals_remaining(state, config)}")
    print("\nItems:")
    for item in all_items():
        print(f"  [{item['status']}] {item['id']} — {item['profile']['title']} ({item['profile']['kind']}), {item.get('post_count', 0)} posts")
    print("\nQueue:")
    for p in queued_posts():
        print(f"  {p['id']} {p['status']:<18} {p['channel']:<10} {p['item_id']}")


def cmd_doctor(args, config):
    """Check what's set up."""
    from .llm import LLMError
    from .publishers import ALL

    try:
        llm = get_llm(config)
        print("AI providers:", ", ".join(p.name for p in llm.providers))
    except LLMError as exc:
        print("AI providers: ❌", exc)
    for name, cls in ALL.items():
        ok = cls.configured()
        missing = [] if ok else [s for s in cls.secrets if not __import__("os").environ.get(s)]
        print(f"{'✅' if ok else '·'} {cls.label:<14} {'' if ok else 'missing: ' + ', '.join(missing)}")


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="marketit", description="AI marketing on autopilot")
    parser.add_argument("--fake-ai", action="store_true", help="use a built-in fake AI (for trying things without keys)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="add a LEGO Ideas project")
    p.add_argument("link", help="https://ideas.lego.com/product-ideas/...")
    p.add_argument("--notes", default="")
    p.set_defaults(fn=cmd_add)

    sub.add_parser("sync", help="(workflow) process item issues and comment commands").set_defaults(fn=cmd_sync)

    sub.add_parser("prepare", help="check watchers and write the next posts").set_defaults(fn=cmd_prepare)

    p = sub.add_parser("publish", help="post everything that's ready")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_publish)

    p = sub.add_parser("run", help="prepare + publish")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("preview", help="show sample posts without posting anything")
    p.add_argument("item_id", nargs="?")
    p.set_defaults(fn=cmd_preview)

    sub.add_parser("stats", help="collect engagement stats now").set_defaults(fn=cmd_stats)
    sub.add_parser("status", help="show items, queue and channels").set_defaults(fn=cmd_status)
    sub.add_parser("doctor", help="check which AI providers and channels are set up").set_defaults(fn=cmd_doctor)

    p = sub.add_parser("approve", help="approve (or --reject) a waiting post")
    p.add_argument("post_id")
    p.add_argument("--text", help="replace the text before approving")
    p.add_argument("--reject", action="store_true")
    p.set_defaults(fn=cmd_approve)

    args = parser.parse_args(argv)
    config = load_config()
    try:
        args.fn(args, config)
    except Exception as exc:
        log.error(redact(str(exc)))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
