"""Catch up on GitHub issues and comments.

Every workflow run calls this, so an item issue or approval comment is never lost, even
if GitHub cancels a queued job (it keeps only the newest pending job per concurrency group).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from .approvals import handle_comment
from . import legoideas
from .intake import ITEM_LABEL, intake_from_issue
from .config import redact
from .llm import LLMError
from .storage import find_item_by_issue, iso, load_state, now, parse_iso, save_item, save_state

log = logging.getLogger(__name__)
OVERLAP = timedelta(minutes=15)
KEEP_PROCESSED = 1000


def body_hash(issue: dict) -> str:
    return hashlib.sha256(((issue.get("title") or "") + "\n" + (issue.get("body") or "")).encode()).hexdigest()[:16]


def allowed(config: dict, association: str | None) -> bool:
    return (association or "").upper() in [a.upper() for a in config["github"]["allowed_associations"]]


def _since(value: str | None) -> str | None:
    t = parse_iso(value)
    return iso(t - OVERLAP) if t else None


def sync_issues(config: dict, llm_factory, gh, state: dict) -> int:
    # Not filtered by label: GitHub drops a form's label if it doesn't exist in the repo yet.
    params = {"state": "all", "sort": "updated", "direction": "asc"}
    since = _since(state.get("issues_synced_at"))
    if since:
        params["since"] = since
    handled = 0
    for issue in gh.paged("issues", params):
        if "pull_request" in issue or not allowed(config, issue.get("author_association")):
            continue
        labels = {l["name"] if isinstance(l, dict) else l for l in issue.get("labels", [])}
        item = find_item_by_issue(issue["number"])
        if not item and ITEM_LABEL not in labels and not legoideas.find_project_url(issue.get("body")):
            continue  # not a MarketIt issue
        if issue["state"] == "closed":
            if item and item["status"] != "ended":
                item["status"] = "ended"
                save_item(item)
                handled += 1
            continue
        digest = body_hash(issue)
        if item and item.get("source", {}).get("issue_hash") == digest:
            if item["status"] == "ended":       # reopened
                item["status"] = "active"
                save_item(item)
                handled += 1
            continue
        failed = state.setdefault("failed_issues", {})
        if failed.get(str(issue["number"])) == digest:
            continue  # already reported as failed; waits for the owner to edit the issue
        if not item:
            gh.react(issue["number"])               # 👍 = received
            if ITEM_LABEL not in labels:
                gh.add_labels(issue["number"], [ITEM_LABEL])
        try:
            llm = llm_factory()
        except LLMError as exc:
            if state.setdefault("no_ai_warned", {}).get(str(issue["number"])) != digest:
                gh.comment(issue["number"], f"⏳ Got it! But I can't start yet: {exc}\n\n"
                           "Add the secret in **Settings → Secrets and variables → Actions**, and I'll pick this up "
                           "automatically on the next run (or run **Actions → MarketIt run → Run workflow**).")
                state["no_ai_warned"][str(issue["number"])] = digest
            continue  # retried automatically once a key is added
        try:
            new = intake_from_issue(llm, config, issue, gh)
        except LLMError as exc:
            warned = state.setdefault("ai_error_warned", {})
            if warned.get(str(issue["number"])) != digest:
                gh.comment(issue["number"], "⏳ Got it, but the AI service had a problem, so I'll retry automatically "
                           f"on the next run (every 3 hours).\n\n<sub>{redact(str(exc))[:400]}</sub>")
                warned[str(issue["number"])] = digest
            continue
        failed.pop(str(issue["number"]), None)
        if new:
            new["source"]["issue_hash"] = digest
            if new["status"] == "ended":
                new["status"] = "active"
            save_item(new)
        else:
            failed[str(issue["number"])] = digest  # don't retry (and re-comment) every run
        handled += 1
    return handled


def sync_comments(config: dict, llm_factory, gh, state: dict) -> int:
    params = {"sort": "created", "direction": "asc"}
    since = _since(state.get("comments_synced_at"))
    if since:
        params["since"] = since
    processed = state.setdefault("processed_comments", [])
    done = set(processed)
    approvals_issue = state.get("approvals_issue")
    handled = 0
    for c in gh.paged("issues/comments", params):
        if c["id"] in done:
            continue
        done.add(c["id"])
        processed.append(c["id"])
        if c.get("user", {}).get("type") == "Bot" or c.get("performed_via_github_app"):
            continue
        if not allowed(config, c.get("author_association")):
            continue
        number = int(c["issue_url"].rsplit("/", 1)[-1])
        if number != approvals_issue and not find_item_by_issue(number):
            continue
        save_state(state)  # handle_comment loads/saves state itself
        handle_comment(llm_factory, config, number, c.get("body", ""), gh, {})
        state.update({k: v for k, v in load_state().items() if k not in ("processed_comments",)})
        handled += 1
    del processed[:-KEEP_PROCESSED]
    return handled


def sync(config: dict, llm_factory, gh) -> dict:
    if gh is None:
        return {"issues": 0, "comments": 0}
    state = load_state()
    started = iso(now())
    issues = sync_issues(config, llm_factory, gh, state)
    state["issues_synced_at"] = started
    save_state(state)
    state = load_state()
    comments = sync_comments(config, llm_factory, gh, state)
    state["comments_synced_at"] = started
    save_state(state)
    return {"issues": issues, "comments": comments}
