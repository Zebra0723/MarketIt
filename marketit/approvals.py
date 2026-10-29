"""The 'first N posts need approval' gate, plus issue-comment commands."""

from __future__ import annotations

import logging
import re

from .config import redact
from .publishers import ALL
from .storage import (archive_post, iso, load_queued, load_state, queued_posts, save_item, save_queued,
                      save_state)
from .textutil import fit_text

log = logging.getLogger(__name__)
APPROVALS_LABEL = "marketit-approvals"


def approvals_remaining(state: dict, config: dict) -> int:
    return max(0, int(config["approvals"]["first_n"]) - int(state.get("approved_count", 0)))


def needs_approval(state: dict, config: dict) -> bool:
    return approvals_remaining(state, config) > 0


def approval_issue(gh, state: dict) -> int | None:
    """Issue used for approving posts of manual items (they have no issue of their own)."""
    if state.get("approvals_issue"):
        return state["approvals_issue"]
    number = gh.create_issue(
        "MarketIt approvals",
        "MarketIt posts approval requests for items that don't have their own issue here.",
        [APPROVALS_LABEL],
    )
    state["approvals_issue"] = number
    return number


def approval_comment(post: dict, item: dict, remaining: int, image_url: str | None) -> str:
    label = ALL[post["channel"]].label
    lines = [
        f"### 📝 Approval needed — {label} post `{post['id']}`",
        f"<sub>{'Milestone' if post['kind'] == 'milestone' else 'Style: ' + str(post.get('style'))} · "
        f"{remaining} more approval(s) until MarketIt runs fully automatically</sub>",
        "",
        *(f"> {l}" if l else ">" for l in post["text"].splitlines()),
        "",
    ]
    if image_url:
        lines += [f'<img src="{image_url}" width="320" alt="{post.get("alt_text", "")[:200]}">', ""]
    lines += [
        "Reply with one of:",
        f"- `approve {post['id']}`",
        f"- `reject {post['id']}`",
        f"- `edit {post['id']}: your new text`",
        "- `approve all` (approves every waiting post on this issue)",
    ]
    return "\n".join(lines)


def request_pending_approvals(gh, state: dict, config: dict, items: dict[str, dict]) -> int:
    """Comment approval requests for waiting posts that haven't been announced yet."""
    if not gh:
        return 0
    sent = 0
    for post in queued_posts():
        if post["status"] != "awaiting_approval" or post.get("approval_issue"):
            continue
        item = items.get(post["item_id"])
        if not item:
            continue
        issue = item.get("source", {}).get("issue") or approval_issue(gh, state)
        if not issue:
            continue
        image_url = gh.file_url(f"data/{post['image']}") if post.get("image") else None
        if gh.comment(issue, approval_comment(post, item, approvals_remaining(state, config), image_url)):
            post["approval_issue"] = issue
            save_queued(post)
            sent += 1
    return sent


# Commands ------------------------------------------------------------------------

POST_CMD = re.compile(r"^\s*(approve|reject)\s+(P[0-9A-F]{6})\b", re.I)
EDIT_CMD = re.compile(r"^\s*edit\s+(P[0-9A-F]{6})\s*:\s*(.+)", re.I | re.S)
ITEM_CMD = re.compile(r"^\s*(pause|resume|stop|status|approve all|approve|reject)\s*$", re.I)
NOTES_CMD = re.compile(r"^\s*notes?\s*:\s*(.+)", re.I | re.S)


def approve(post: dict, state: dict, text: str | None = None) -> dict:
    if text:
        text = fit_text(text.strip(), ALL[post["channel"]].max_chars, post.get("link"))
        post["text"] = text
        post["edited"] = True
    post["status"] = "ready"
    post["approved_at"] = iso()
    state["approved_count"] = state.get("approved_count", 0) + 1
    save_queued(post)
    return post


def reject(post: dict) -> dict:
    post["status"] = "rejected"
    archive_post(post)
    return post


def parse_commands(body: str) -> list[tuple]:
    """Returns a list of (command, post_id_or_None, extra_text)."""
    body = body.strip()
    m = EDIT_CMD.match(body)
    if m:
        return [("edit", m.group(1).upper(), m.group(2).strip())]
    m = NOTES_CMD.match(body)
    if m:
        return [("notes", None, m.group(1).strip())]
    out = []
    for line in body.splitlines():
        m = POST_CMD.match(line)
        if m:
            out.append((m.group(1).lower(), m.group(2).upper(), ""))
            continue
        m = ITEM_CMD.match(line)
        if m:
            out.append((m.group(1).lower(), None, ""))
    return out


def handle_comment(llm_factory, config: dict, issue_number: int, body: str, gh, items_by_issue: dict) -> list[str]:
    """Run the commands in an issue comment. Returns reply lines (also posted to the issue)."""
    from .intake import summary_markdown, update_notes
    from .storage import find_item_by_issue

    state = load_state()
    replies = []
    waiting_here = [p for p in queued_posts() if p["status"] == "awaiting_approval" and p.get("approval_issue") == issue_number]
    item = find_item_by_issue(issue_number)

    for cmd, post_id, extra in parse_commands(body):
        if cmd in ("approve", "reject", "edit") and post_id:
            post = load_queued(post_id)
            if not post or post["status"] != "awaiting_approval":
                replies.append(f"⚠️ `{post_id}` isn't waiting for approval.")
                continue
            if cmd == "approve":
                approve(post, state)
                replies.append(f"👍 `{post_id}` approved — posting now.")
            elif cmd == "edit":
                approve(post, state, extra)
                replies.append(f"✏️ `{post_id}` updated and approved — posting now.")
            else:
                reject(post)
                replies.append(f"🗑️ `{post_id}` rejected. I'll write a different one next run.")
        elif cmd in ("approve all", "approve") and not post_id:
            if cmd == "approve" and len(waiting_here) > 1:
                replies.append("⚠️ Several posts are waiting here — use `approve <id>` or `approve all`.")
                continue
            for post in waiting_here:
                approve(post, state)
            replies.append(f"👍 Approved {len(waiting_here)} post(s) — posting now." if waiting_here else "Nothing is waiting for approval here.")
        elif cmd == "reject" and not post_id:
            if len(waiting_here) == 1:
                reject(waiting_here[0])
                replies.append(f"🗑️ `{waiting_here[0]['id']}` rejected.")
            else:
                replies.append("⚠️ Use `reject <id>`.")
        elif item and cmd in ("pause", "resume", "stop"):
            item["status"] = {"pause": "paused", "resume": "active", "stop": "ended"}[cmd]
            save_item(item)
            replies.append({"pause": "⏸️ Paused.", "resume": "▶️ Resumed.", "stop": "⏹️ Stopped for good (comment `resume` to undo)."}[cmd])
        elif item and cmd == "status":
            replies.append(status_markdown(item, config))
        elif item and cmd == "notes":
            try:
                updated = update_notes(llm_factory(), config, item, extra)
                replies.append("📝 Notes added.\n\n" + summary_markdown(updated, config))
            except Exception as exc:
                replies.append(f"❌ Couldn't apply those notes: `{redact(str(exc))[:300]}`")
    save_state(state)
    if replies and gh:
        gh.comment(issue_number, "\n\n".join(replies))
    return replies


def status_markdown(item: dict, config: dict) -> str:
    from .storage import history_posts

    posts = [p for p in history_posts() if p["item_id"] == item["id"] and p["status"] == "published"]
    lines = [f"### 📊 {item['profile']['title']} — {item['status']}", f"Published posts: **{len(posts)}**"]
    for p in posts[-5:]:
        m = p.get("metrics") or {}
        lines.append(f"- {ALL[p['channel']].label}: {p.get('url') or p['id']} — ❤️ {m.get('likes', '?')} 🔁 {m.get('reposts', '?')} 💬 {m.get('replies', '?')}")
    for w in item.get("watchers", []):
        last = w["history"][-1]["v"] if w.get("history") else "not checked yet"
        lines.append(f"- 👀 {w['metric']}: **{last:,.0f}**" if isinstance(last, (int, float)) else f"- 👀 {w['metric']}: {last}")
        if w.get("last_error"):
            lines.append(f"  - ⚠️ {w['last_error']}")
    return "\n".join(lines)

