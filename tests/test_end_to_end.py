"""Full flow with a fake AI and fake websites: issue -> approval -> publish -> milestone."""

import random

from marketit import runner
from marketit.approvals import handle_comment
from marketit.intake import intake_from_issue, sync_manual_items
from marketit.storage import all_items, history_posts, load_state, queued_posts

from .conftest import FakeResponse, png_bytes

LEGO = "https://ideas.lego.com/projects/123-castle"


def lego_page(supporters):
    return FakeResponse(text=f"""<html><head>
      <meta property="og:title" content="Floating Castle">
      <meta property="og:description" content="A castle on a cloud, made of LEGO bricks.">
      <meta property="og:image" content="https://cdn.test/castle.jpg">
      </head><body><h1>Floating Castle</h1><div>{supporters}</div><div>Supporters</div>
      <p>{"A whimsical build with towers, a drawbridge and a cloud base. " * 10}</p></body></html>""")


class FakeGitHub:
    def __init__(self):
        self.comments = []
        self.repo = "me/marketit"

    def comment(self, issue, body):
        self.comments.append((issue, body))
        return len(self.comments)

    def create_issue(self, title, body, labels):
        return 99

    def file_url(self, path):
        return f"https://github.com/me/marketit/blob/main/{path}?raw=true"

    def repo_is_public(self):
        return False


def setup_bluesky(web, monkeypatch):
    monkeypatch.setenv("BLUESKY_HANDLE", "me.bsky.social")
    monkeypatch.setenv("BLUESKY_APP_PASSWORD", "app-pass-1234")
    web.on("POST", "https://bsky.social/xrpc/com.atproto.server.createSession",
           {"accessJwt": "jwt", "did": "did:plc:me", "handle": "me.bsky.social"})
    web.on("POST", "https://bsky.social/xrpc/com.atproto.repo.uploadBlob", {"blob": {"$type": "blob", "ref": "x"}})
    counter = {"n": 0}

    def create(url, kw):
        counter["n"] += 1
        return {"uri": f"at://did:plc:me/app.bsky.feed.post/rkey{counter['n']}", "cid": "c"}

    web.on("POST", "https://bsky.social/xrpc/com.atproto.repo.createRecord", create)


def test_full_flow(web, monkeypatch, config, fake_llm):
    monkeypatch.setenv("MARKETIT_NOW", "2026-05-01T09:00:00+00:00")
    config["approvals"]["first_n"] = 1
    setup_bluesky(web, monkeypatch)
    web.on("GET", LEGO, lego_page("850"))
    web.on("GET", "https://cdn.test/castle.jpg", FakeResponse(content=png_bytes()))
    gh = FakeGitHub()

    # 1. Owner opens an issue with a link + notes.
    issue = {"number": 7, "body": f"### Link\n\n{LEGO}\n\n### Notes\n\nmake a special post when we hit 1k supporters\n\n### Images\n\nauto"}
    item = intake_from_issue(fake_llm, config, issue, gh)
    assert item["id"] == "7-floating-castle"
    assert item["profile"]["kind"] == "lego_ideas_project"
    assert item["watchers"][0]["triggers"][0]["value"] == 1000
    assert "Got it: **Floating Castle**" in gh.comments[-1][1]
    assert "Reddit drafts" in gh.comments[-1][1]

    # 2. First run: watcher reads 850 (no milestone); first post waits for approval.
    summary = runner.prepare(config, fake_llm, random.Random(0))
    assert summary == {"milestones": 0, "queued": 1, "errors": []}
    [post] = queued_posts()
    assert post["status"] == "awaiting_approval" and post["image"].startswith("media/")
    assert LEGO in post["text"]
    result = runner.publish_queue(config, gh)
    assert result["published"] == []
    assert "Approval needed" in gh.comments[-1][1] and gh.comments[-1][0] == 7

    # 3. Owner approves by commenting; it gets published.
    handle_comment(lambda: fake_llm, config, 7, f"approve {post['id']}", gh, {})
    result = runner.publish_queue(config, gh)
    assert [p["id"] for p in result["published"]] == [post["id"]]
    assert result["published"][0]["url"] == "https://bsky.app/profile/me.bsky.social/post/rkey1"
    assert load_state()["approved_count"] == 1

    # 4. Next day the project passes 1,000 supporters: milestone posts automatically, once.
    monkeypatch.setenv("MARKETIT_NOW", "2026-05-02T10:00:00+00:00")
    web.on("GET", LEGO, lego_page("1,020"))
    summary = runner.prepare(config, fake_llm, random.Random(0))
    assert summary["milestones"] == 1
    milestone = [p for p in queued_posts() if p["kind"] == "milestone"][0]
    assert milestone["status"] == "ready" and "1,000 supporters!" in milestone["text"]
    runner.publish_queue(config, gh)
    assert any("Milestone posted" in body for _, body in gh.comments)

    monkeypatch.setenv("MARKETIT_NOW", "2026-05-03T11:00:00+00:00")
    web.on("GET", LEGO, lego_page("1,100"))
    assert runner.prepare(config, fake_llm, random.Random(0))["milestones"] == 0

    published = [p for p in history_posts() if p["status"] == "published"]
    assert {p["kind"] for p in published} == {"regular", "milestone"}


def test_manual_item_and_stats(web, monkeypatch, config, fake_llm, tmp_path):
    monkeypatch.setenv("MARKETIT_NOW", "2026-06-01T09:00:00+00:00")
    config["approvals"]["first_n"] = 0
    setup_bluesky(web, monkeypatch)
    (tmp_path / "items" / "candle.yaml").write_text(
        "name: Lavender Candle\ndescription: Hand-poured soy candle.\nprice: $12\nnotes: be cozy\nimage_mode: ai\n"
    )
    assert sync_manual_items(fake_llm, config) == ["manual-candle"]
    assert sync_manual_items(fake_llm, config) == []          # unchanged file -> no work

    runner.prepare(config, fake_llm, random.Random(0))
    [post] = queued_posts()
    assert post["status"] == "ready" and post["image"]       # template card since AI images are off
    runner.publish_queue(config, None)

    web.on("GET", "https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts",
           {"posts": [{"likeCount": 10, "repostCount": 2, "replyCount": 1}]})
    monkeypatch.setenv("MARKETIT_NOW", "2026-06-03T09:00:00+00:00")
    assert runner.collect_stats(config, force=True) == 1
    state = load_state()
    assert state["style_scores"]["bluesky"][post["style"]]["n"] == 1


def test_publish_failure_is_reported_and_secrets_redacted(web, monkeypatch, config, fake_llm):
    monkeypatch.setenv("MARKETIT_NOW", "2026-06-01T09:00:00+00:00")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:SECRETSECRET")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@mychan")
    config["approvals"]["first_n"] = 0
    web.on("GET", LEGO, lego_page("10"))
    web.on("GET", "https://cdn.test/castle.jpg", FakeResponse(content=png_bytes()))
    web.on("POST", "https://api.telegram.org/", FakeResponse(401, text="Unauthorized"))
    gh = FakeGitHub()
    intake_from_issue(fake_llm, config, {"number": 3, "body": LEGO}, gh)
    runner.prepare(config, fake_llm, random.Random(0))
    result = runner.publish_queue(config, gh)
    assert len(result["failed"]) == 1
    assert "SECRETSECRET" not in result["failed"][0]["last_error"]
    assert any("Couldn't post to Telegram" in b for _, b in gh.comments)


def test_item_commands(web, monkeypatch, config, fake_llm):
    web.on("GET", LEGO, lego_page("10"))
    gh = FakeGitHub()
    intake_from_issue(fake_llm, config, {"number": 5, "body": LEGO}, gh)
    handle_comment(lambda: fake_llm, config, 5, "pause", gh, {})
    assert all_items()[0]["status"] == "paused"
    handle_comment(lambda: fake_llm, config, 5, "resume", gh, {})
    assert all_items()[0]["status"] == "active"
    handle_comment(lambda: fake_llm, config, 5, "notes: post when we hit 5k supporters", gh, {})
    assert all_items()[0]["watchers"][0]["triggers"][0]["value"] == 5000


class SyncGitHub(FakeGitHub):
    def __init__(self):
        super().__init__()
        self.issues, self.issue_comments = [], []

    def paged(self, path, params):
        return list(self.issues if path == "issues" else self.issue_comments)


def test_sync_catches_up_on_issues_and_comments(web, monkeypatch, config, fake_llm):
    from marketit.sync import sync

    monkeypatch.setenv("MARKETIT_NOW", "2026-07-01T09:00:00+00:00")
    config["approvals"]["first_n"] = 1
    setup_bluesky(web, monkeypatch)
    web.on("GET", LEGO, lego_page("100"))
    web.on("GET", "https://cdn.test/castle.jpg", FakeResponse(content=png_bytes()))
    gh = SyncGitHub()
    mine = {"number": 11, "state": "open", "title": "Market: castle", "body": LEGO, "author_association": "OWNER"}
    stranger = {"number": 12, "state": "open", "title": "spam", "body": "https://spam.test", "author_association": "NONE"}
    gh.issues = [mine, stranger]

    assert sync(config, lambda: fake_llm, gh)["issues"] == 1
    assert [i["source"]["issue"] for i in all_items()] == [11]
    assert sync(config, lambda: fake_llm, gh)["issues"] == 0          # unchanged -> nothing to do

    runner.prepare(config, fake_llm, random.Random(0))
    runner.publish_queue(config, gh)
    [post] = queued_posts()
    gh.issue_comments = [
        {"id": 1, "issue_url": "https://api.github.com/repos/me/marketit/issues/11", "body": f"approve {post['id']}",
         "author_association": "OWNER", "user": {"type": "User"}},
        {"id": 2, "issue_url": "https://api.github.com/repos/me/marketit/issues/11", "body": "approve all",
         "author_association": "NONE", "user": {"type": "User"}},
    ]
    assert sync(config, lambda: fake_llm, gh)["comments"] == 1
    assert sync(config, lambda: fake_llm, gh)["comments"] == 0        # each comment handled once
    assert runner.publish_queue(config, gh)["published"][0]["id"] == post["id"]

    mine["state"] = "closed"
    sync(config, lambda: fake_llm, gh)
    assert all_items()[0]["status"] == "ended"
