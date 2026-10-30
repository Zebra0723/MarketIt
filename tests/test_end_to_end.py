"""Full flow with a fake AI and a fake LEGO Ideas page: issue -> approval -> publish -> milestone."""

import random

from PIL import Image

from marketit import runner
from marketit.approvals import handle_comment
from marketit.intake import intake_from_issue, sync_manual_items
from marketit.storage import all_items, data_dir, history_posts, load_state, queued_posts

from .conftest import FakeResponse

LEGO = "https://ideas.lego.com/projects/a6b7e5c1-6d8e-4c1e-8a3b-2a1f1d0e9c11"
PHOTOS = {
    "https://cdn.test/castle-main.jpg": (1600, 1200),
    "https://cdn.test/castle-side.jpg": (1600, 900),
    "https://cdn.test/castle-detail.jpg": (1000, 1000),
}


def lego_page(supporters, days_left=214):
    imgs = "".join(f'<img src="{u}">' for u in list(PHOTOS)[1:])
    return FakeResponse(text=f"""<html><head>
      <title>Floating Castle | LEGO Ideas</title>
      <meta property="og:title" content="Floating Castle | LEGO Ideas">
      <meta property="og:description" content="A castle on a cloud, made of LEGO bricks.">
      <meta property="og:image" content="{list(PHOTOS)[0]}">
      </head><body><h1>Floating Castle</h1><div>Created by</div><div>BrickWizard42</div>
      <div>{supporters}</div><div>Supporters</div><div>{days_left} days left</div>{imgs}
      <p>{"A whimsical build with towers, a drawbridge and a cloud base. " * 10}</p></body></html>""")


def jpeg_bytes(size):
    import io
    buf = io.BytesIO()
    Image.new("RGB", size, (90, 120, 200)).save(buf, "JPEG", quality=90)
    return buf.getvalue()


def serve_lego(web, supporters, days_left=214):
    web.on("GET", LEGO, lego_page(supporters, days_left))
    for url, size in PHOTOS.items():
        web.on("GET", url, FakeResponse(content=jpeg_bytes(size)))


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

    def react(self, issue, content="+1"):
        self.reactions = getattr(self, "reactions", []) + [(issue, content)]

    def add_labels(self, issue, labels):
        self.labels = getattr(self, "labels", []) + [(issue, labels)]


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
    serve_lego(web, "850")
    gh = FakeGitHub()

    # 1. Owner opens an issue with a LEGO Ideas link + notes.
    issue = {"number": 7, "body": f"### LEGO Ideas link\n\n{LEGO}/updates\n\n### Notes\n\nalso celebrate 1,500 supporters"}
    item = intake_from_issue(fake_llm, config, issue, gh)
    assert item["id"] == "7-floating-castle"
    assert item["profile"]["link"] == LEGO
    assert item["profile"]["images"] == list(PHOTOS)
    assert item["project"]["supporters"] == 850 and item["project"]["creator"] == "BrickWizard42"
    milestones = [t["value"] for t in item["watchers"][0]["triggers"]]
    assert 1000 in milestones and 1500 in milestones and 10000 in milestones
    reply = gh.comments[-1][1]
    assert "Got it: **Floating Castle**" in reply and "1,000, 1,500, 2,000" in reply

    # 2. First run: the first post waits for approval; it has the ad + the original photos.
    summary = runner.prepare(config, fake_llm, random.Random(0))
    assert summary == {"milestones": 0, "queued": 1, "errors": []}
    [post] = queued_posts()
    assert post["status"] == "awaiting_approval" and LEGO in post["text"]
    assert len(post["extra_images"]) == 3
    with Image.open(data_dir() / post["image"]) as ad:
        assert ad.size == (1080, 1350)
    # The extra photos are the project's original files, byte for byte.
    assert (data_dir() / post["extra_images"][0]).read_bytes() == jpeg_bytes(PHOTOS["https://cdn.test/castle-main.jpg"])
    runner.publish_queue(config, gh)
    assert "Approval needed" in gh.comments[-1][1]

    # 3. Owner approves; it's published with 4 images (ad + 3 project photos).
    handle_comment(lambda: fake_llm, config, 7, f"approve {post['id']}", gh, {})
    result = runner.publish_queue(config, gh)
    assert [p["id"] for p in result["published"]] == [post["id"]]
    record = web.calls_to("https://bsky.social/xrpc/com.atproto.repo.createRecord")[-1][2]["json"]
    assert len(record["record"]["embed"]["images"]) == 4
    assert load_state()["approved_count"] == 1

    # 4. Seven hours later the project passes 1,000: a milestone post goes out automatically, once.
    monkeypatch.setenv("MARKETIT_NOW", "2026-05-01T16:00:00+00:00")
    serve_lego(web, "1,020")
    summary = runner.prepare(config, fake_llm, random.Random(0))
    assert summary["milestones"] == 1
    milestone = [p for p in queued_posts() if p["kind"] == "milestone"][0]
    assert milestone["status"] == "ready" and milestone["template"] == "milestone"
    assert "1,000 supporters!" in milestone["text"]
    assert all_items()[0]["project"]["supporters"] == 1020
    runner.publish_queue(config, gh)
    assert any("Milestone posted" in body for _, body in gh.comments)

    monkeypatch.setenv("MARKETIT_NOW", "2026-05-02T11:00:00+00:00")
    serve_lego(web, "1,100")
    assert runner.prepare(config, fake_llm, random.Random(0))["milestones"] == 0

    # 5. Countdown: 7 days left triggers a countdown ad.
    monkeypatch.setenv("MARKETIT_NOW", "2026-05-03T11:00:00+00:00")
    serve_lego(web, "1,150", days_left=7)
    runner.prepare(config, fake_llm, random.Random(0))
    countdown = [p for p in queued_posts() if p["kind"] == "milestone" and p["template"] == "countdown"]
    assert countdown

    published = [p for p in history_posts() if p["status"] == "published"]
    assert {p["kind"] for p in published} == {"regular", "milestone"}


def test_non_lego_links_are_rejected(web, config, fake_llm):
    gh = FakeGitHub()
    assert intake_from_issue(fake_llm, config, {"number": 2, "body": "https://www.etsy.com/listing/1"}, gh) is None
    assert "LEGO Ideas project links" in gh.comments[-1][1]
    assert all_items() == []


def test_no_photos_means_no_post(web, monkeypatch, config, fake_llm):
    monkeypatch.setenv("MARKETIT_NOW", "2026-06-01T09:00:00+00:00")
    config["approvals"]["first_n"] = 0
    setup_bluesky(web, monkeypatch)
    web.on("GET", LEGO, FakeResponse(text="<html><body>Castle 10 supporters 30 days left " + "x " * 300 + "</body></html>"))
    intake_from_issue(fake_llm, config, {"number": 4, "body": LEGO}, FakeGitHub())
    summary = runner.prepare(config, fake_llm, random.Random(0))
    assert summary["queued"] == 0 and "no project photos" in summary["errors"][0]
    assert queued_posts() == []


def test_file_item_and_stats(web, monkeypatch, config, fake_llm, tmp_path):
    monkeypatch.setenv("MARKETIT_NOW", "2026-06-01T09:00:00+00:00")
    config["approvals"]["first_n"] = 0
    setup_bluesky(web, monkeypatch)
    serve_lego(web, "300")
    (tmp_path / "items" / "castle.yaml").write_text(f"link: {LEGO}\nnotes: be cozy\n")
    assert sync_manual_items(fake_llm, config) == ["file-castle"]
    assert sync_manual_items(fake_llm, config) == []          # unchanged file -> no work

    runner.prepare(config, fake_llm, random.Random(0))
    [post] = queued_posts()
    assert post["status"] == "ready" and post["image"]
    runner.publish_queue(config, None)

    web.on("GET", "https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts",
           {"posts": [{"likeCount": 10, "repostCount": 2, "replyCount": 1}]})
    monkeypatch.setenv("MARKETIT_NOW", "2026-06-03T09:00:00+00:00")
    assert runner.collect_stats(config, force=True) == 1
    assert load_state()["style_scores"]["bluesky"][post["style"]]["n"] == 1


def test_publish_failure_is_reported_and_secrets_redacted(web, monkeypatch, config, fake_llm):
    monkeypatch.setenv("MARKETIT_NOW", "2026-06-01T09:00:00+00:00")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:SECRETSECRET")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@mychan")
    config["approvals"]["first_n"] = 0
    serve_lego(web, "10")
    web.on("POST", "https://api.telegram.org/", FakeResponse(401, text="Unauthorized"))
    gh = FakeGitHub()
    intake_from_issue(fake_llm, config, {"number": 3, "body": LEGO}, gh)
    runner.prepare(config, fake_llm, random.Random(0))
    result = runner.publish_queue(config, gh)
    assert len(result["failed"]) == 1
    assert "SECRETSECRET" not in result["failed"][0]["last_error"]
    assert any("Couldn't post to Telegram" in b for _, b in gh.comments)


def test_item_commands(web, monkeypatch, config, fake_llm):
    serve_lego(web, "10")
    gh = FakeGitHub()
    intake_from_issue(fake_llm, config, {"number": 5, "body": LEGO}, gh)
    handle_comment(lambda: fake_llm, config, 5, "pause", gh, {})
    assert all_items()[0]["status"] == "paused"
    handle_comment(lambda: fake_llm, config, 5, "resume", gh, {})
    assert all_items()[0]["status"] == "active"
    handle_comment(lambda: fake_llm, config, 5, "notes: also celebrate 1,750 supporters", gh, {})
    assert 1750 in [t["value"] for t in all_items()[0]["watchers"][0]["triggers"]]


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
    serve_lego(web, "100")
    gh = SyncGitHub()
    mine = {"number": 11, "state": "open", "title": "Promote: castle", "body": LEGO, "author_association": "OWNER"}
    stranger = {"number": 12, "state": "open", "title": "spam", "body": LEGO, "author_association": "NONE"}
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


def test_unlabelled_product_ideas_issue_is_picked_up_with_thumbs_up(web, monkeypatch, config, fake_llm):
    """GitHub drops a form's label if it doesn't exist yet: the issue must still be found by its link."""
    from marketit.llm import LLMError
    from marketit.sync import sync

    link = "https://ideas.lego.com/product-ideas/6726571d-0a01-411f-b5ac-425634ecf4e5"
    web.on("GET", link, lego_page("42"))
    for url, size in PHOTOS.items():
        web.on("GET", url, FakeResponse(content=jpeg_bytes(size)))
    gh = SyncGitHub()
    gh.issues = [{"number": 1, "state": "open", "title": "LEGO Ideas: The Golden Gate Bridge", "labels": [],
                  "body": f"### LEGO Ideas link\n\n{link}\n\n### Notes\n\nadvertise it to lego communities",
                  "author_association": "OWNER"},
                 {"number": 2, "state": "open", "title": "unrelated bug", "labels": [], "body": "hi",
                  "author_association": "OWNER"}]

    # No AI key yet: acknowledged with 👍 and a helpful comment (once), not silence.
    def no_key():
        raise LLMError("No AI provider is configured. Add a free GEMINI_API_KEY")
    sync(config, no_key, gh)
    sync(config, no_key, gh)
    assert gh.reactions[0] == (1, "+1") and (1, ["marketit-item"]) in gh.labels
    assert sum("GEMINI_API_KEY" in b for _, b in gh.comments) == 1
    assert all_items() == []

    # AI overloaded: told once, and a question on the issue gets a status reply.
    def busy():
        class Busy:
            def complete(self, *a, **k):
                raise LLMError("Gemini is overloaded right now")
        return Busy()
    sync(config, busy, gh)
    gh.issue_comments = [{"id": 9, "issue_url": "https://api.github.com/repos/me/marketit/issues/1",
                          "body": "is it working now?", "author_association": "OWNER", "user": {"type": "User"}}]
    sync(config, busy, gh)
    assert "Not set up yet" in gh.comments[-1][1] and "overloaded" in gh.comments[-1][1]
    gh.issue_comments = []

    # Key added: picked up automatically on the next run.
    sync(config, lambda: fake_llm, gh)
    [item] = all_items()
    assert item["profile"]["link"] == link and item["source"]["issue"] == 1
    assert "Got it" in gh.comments[-1][1]
