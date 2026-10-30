import random

from marketit import learning, planner
from marketit.intake.fetch import parse_html
from marketit.intake.issue_form import parse_issue_form
from marketit.publishers.bluesky import build_facets
from marketit.publishers.x import oauth1_header
from marketit.storage import load_state
from marketit.textutil import extract_json, fit_text, parse_number
from marketit.watchers import evaluate, extract_metric_regex


def test_parse_number():
    assert parse_number("1,234") == 1234
    assert parse_number("1.234") == 1234
    assert parse_number("1.5k") == 1500
    assert parse_number("3M") == 3_000_000
    assert parse_number("42") == 42
    assert parse_number("abc") is None


def test_extract_json_handles_fences_and_chatter():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here you go: {"a": [1, 2]} hope that helps') == {"a": [1, 2]}


def test_fit_text_keeps_link():
    link = "https://example.com/thing"
    out = fit_text("word " * 100, 120, link)
    assert len(out) <= 120 and out.endswith(link)
    assert fit_text("short", 100, link) == f"short\n\n{link}"


def test_issue_form_parsing():
    body = (
        "### LEGO Ideas link\n\nhttps://ideas.lego.com/projects/abc\n\n"
        "### Notes\n\n_No response_"
    )
    assert parse_issue_form(body) == {"link": "https://ideas.lego.com/projects/abc", "notes": ""}


def test_plain_issue_body_is_understood():
    form = parse_issue_form("please market https://x.com/thing and be funny")
    assert form["link"] == "https://x.com/thing"
    assert "be funny" in form["notes"]


def test_parse_html_extracts_meta_price_and_images():
    html = """<html><head><title>T</title>
      <meta property="og:title" content="Cool Mug">
      <meta property="og:description" content="A mug that is cool.">
      <meta property="og:image" content="/img/mug.jpg">
      <script type="application/ld+json">{"@type":"Product","offers":{"price":"19.99","priceCurrency":"USD"}}</script>
      </head><body><img src="/logo.png"><img src="/img/side.jpg" width="600"><p>Great mug.</p></body></html>"""
    page = parse_html("https://shop.test/mug", html)
    assert page.title == "Cool Mug"
    assert page.price == "19.99 USD"
    assert page.images == ["https://shop.test/img/mug.jpg", "https://shop.test/img/side.jpg"]
    assert "Great mug." in page.text


def test_metric_regex():
    assert extract_metric_regex("Castle\n1,234\nSupporters\n120 days left", "supporters") == 1234
    assert extract_metric_regex("Supporters: 2.5K", "supporters") == 2500
    assert extract_metric_regex("120 days left", "days left") == 120
    assert extract_metric_regex("nothing here", "supporters") is None


def _watcher(*triggers):
    return {"id": "w1", "metric": "supporters", "triggers": list(triggers), "history": [], "fired": []}


def test_threshold_fires_once_and_skips_already_passed():
    w = _watcher({"id": "t1", "op": ">=", "value": 1000}, {"id": "t2", "op": ">=", "value": 100})
    assert evaluate(w, 500) == []          # first reading: 100 already passed -> silent
    assert evaluate(w, 900) == []
    events = evaluate(w, 1001)
    assert [e["trigger_id"] for e in events] == ["t1"]
    assert events[0]["label"] == "1,000 supporters!"
    assert evaluate(w, 1100) == []         # never twice


def test_every_trigger_and_glitch_protection():
    w = _watcher({"id": "t1", "op": "every", "value": 1000})
    evaluate(w, 1500)
    assert evaluate(w, 1900) == []
    assert [e["threshold"] for e in evaluate(w, 2100)] == [2000]
    assert evaluate(w, 50) == []           # implausible drop is held back
    assert w["history"][-1]["v"] == 2100
    assert [e["threshold"] for e in evaluate(w, 3050)] == [3000]


def test_increase_trigger(monkeypatch):
    w = _watcher({"id": "t1", "op": "increase", "value": 100, "window_hours": 24})
    monkeypatch.setenv("MARKETIT_NOW", "2026-01-01T00:00:00+00:00")
    evaluate(w, 1000)
    monkeypatch.setenv("MARKETIT_NOW", "2026-01-01T12:00:00+00:00")
    events = evaluate(w, 1150)
    assert events and events[0]["label"] == "+150 supporters in 24h"
    monkeypatch.setenv("MARKETIT_NOW", "2026-01-01T15:00:00+00:00")
    assert evaluate(w, 1300) == []         # cooldown


def test_bluesky_facets_use_utf8_byte_offsets():
    text = "🎉 new! https://a.co/x #Lego"
    facets = build_facets(text)
    encoded = text.encode()
    link, tag = facets
    assert encoded[link["index"]["byteStart"]:link["index"]["byteEnd"]] == b"https://a.co/x"
    assert encoded[tag["index"]["byteStart"]:tag["index"]["byteEnd"]] == b"#Lego"
    assert tag["features"][0]["tag"] == "Lego"


def test_oauth_header_shape():
    h = oauth1_header("POST", "https://api.x.com/2/tweets", "k", "s", "t", "ts", nonce="n", timestamp="1")
    assert h.startswith("OAuth ") and 'oauth_signature="' in h and 'oauth_nonce="n"' in h


def _item(i, channels=("bluesky",)):
    return {"id": f"item{i}", "status": "active", "last_posted": {}, "post_count": 0,
            "strategy": {"channels": list(channels), "posts_per_week": 3}}


def test_planner_rotates_and_respects_caps(monkeypatch):
    monkeypatch.setenv("MARKETIT_NOW", "2026-03-01T09:00:00+00:00")
    state = load_state()
    items = [_item(1), _item(2)]
    items[0]["last_posted"]["bluesky"] = "2026-02-27T09:00:00+00:00"
    assert planner.pick_item(items, "bluesky", ["bluesky"], [], 20)["id"] == "item2"   # never posted wins
    assert planner.channel_due(state, "bluesky", 2)
    planner.mark_channel_used(state, "bluesky", 2)
    assert not planner.channel_due(state, "bluesky", 2)                                # spacing
    monkeypatch.setenv("MARKETIT_NOW", "2026-03-01T20:00:00+00:00")
    assert planner.channel_due(state, "bluesky", 2)
    planner.mark_channel_used(state, "bluesky", 2)
    monkeypatch.setenv("MARKETIT_NOW", "2026-03-01T23:59:00+00:00")
    assert not planner.channel_due(state, "bluesky", 2)                                # daily cap
    monkeypatch.setenv("MARKETIT_NOW", "2026-03-02T10:00:00+00:00")
    assert planner.channel_due(state, "bluesky", 2)


def test_planner_weekly_quota_and_fallback_channels(monkeypatch):
    monkeypatch.setenv("MARKETIT_NOW", "2026-03-10T09:00:00+00:00")
    item = _item(1, channels=("pinterest",))
    recent = [{"item_id": "item1", "channel": "discord", "kind": "regular", "created_at": f"2026-03-0{d}T09:00:00+00:00"}
              for d in (6, 7, 8)]
    # Item's preferred channel isn't connected -> falls back to what is connected.
    assert planner.item_channels(item, ["discord"]) == ["discord"]
    assert planner.pick_item([item], "discord", ["discord"], recent, 20) is None      # 3/week used


def test_style_choice_exploits_winner():
    state = {"style_scores": {"bluesky": {"imagine": {"n": 5, "mean": 2.0}, "question": {"n": 5, "mean": 0.5}}}}
    rng = random.Random(1)
    picks = [learning.choose_style(state, "bluesky", rng, 0.0) for _ in range(10)]
    assert set(picks) == {"imagine"}
    assert learning.choose_style(state, "bluesky", rng, 0.0, avoid="imagine") == "question"


# LEGO Ideas -------------------------------------------------------------------------

from marketit import legoideas  # noqa: E402
from marketit.images import ads  # noqa: E402

PROJECT = "https://ideas.lego.com/projects/a6b7e5c1-6d8e-4c1e-8a3b-2a1f1d0e9c11"


def test_project_urls():
    assert legoideas.is_project_url(PROJECT)
    assert legoideas.is_project_url(PROJECT + "/updates")
    assert not legoideas.is_project_url("https://ideas.lego.com/challenges/123")
    assert not legoideas.is_project_url("https://example.com/projects/a6b7e5c1")
    assert legoideas.canonical_url(PROJECT + "/comments?page=2") == PROJECT
    assert legoideas.short_url(PROJECT) == "ideas.lego.com/projects/a6b7e5c1…"
    new = "https://ideas.lego.com/product-ideas/6726571d-0a01-411f-b5ac-425634ecf4e5"
    assert legoideas.is_project_url(new)
    assert legoideas.canonical_url(new + "/updates") == new
    assert legoideas.short_url(new) == "ideas.lego.com/product-ideas/6726571d…"
    assert legoideas.find_project_url(f"see {new} thanks") == new


def test_parse_stats_from_page_text():
    text = "Floating Castle\nCreated by\nBrickWizard42\n1,046\nSupporters\n214 days left\n"
    assert legoideas.parse_stats(text) == {"supporters": 1046, "days_left": 214, "creator": "BrickWizard42"}
    assert legoideas.parse_stats("nothing")["supporters"] is None


def test_milestone_maths():
    assert legoideas.next_milestone(None) == 100
    assert legoideas.next_milestone(1046) == 2000
    assert legoideas.next_milestone(12000) == 10000
    assert legoideas.stage_progress(100) == 0.25
    assert legoideas.stage_progress(5000) == 0.75
    assert legoideas.stage_progress(20000) == 1.0


def _marked_photo(size):
    """A photo whose four corners have distinct colours, so cropping would be detectable."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", size, (128, 128, 128))
    d = ImageDraw.Draw(im)
    w, h = size
    k = 40
    for (x, y), c in zip([(0, 0), (w - k, 0), (0, h - k), (w - k, h - k)],
                         [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]):
        d.rectangle([x, y, x + k, y + k], fill=c)
    return im


def _find(ad, color):
    px = ad.load()
    return any(px[x, y] == color for x in range(0, ad.width, 2) for y in range(0, ad.height, 2))


def test_ads_show_whole_uncropped_photos():
    info = {"title": "Castle", "creator": "Bob", "supporters": 1046, "days_left": 9, "url": PROJECT}
    for photo in (_marked_photo((1600, 900)), _marked_photo((900, 1600))):
        for ad in (ads.milestone_ad([photo], info, 1000), ads.progress_ad([photo], info, "A castle"),
                   ads.countdown_ad([photo], info, 7), ads.milestone_ad([photo], info, 1000, h=1620)):
            assert ad.size[0] == 1080
            for corner in [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]:
                assert _find(ad, corner), f"corner {corner} cropped away"
    gallery = ads.gallery_ad([_marked_photo((1600, 1200)), _marked_photo((1200, 900)), _marked_photo((800, 800))], info, "Hi")
    for corner in [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]:
        assert _find(gallery, corner)


def test_ads_refuse_without_photos():
    import pytest
    with pytest.raises(ads.NoPhotosError):
        ads.progress_ad([], {"title": "x", "url": PROJECT}, "x")


def test_headline_balancing_avoids_orphans():
    from PIL import Image, ImageDraw
    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    fnt, lines = ads.fit_headline(draw, "Three towers, one secret dragon lair", 920, start=60, minimum=42)
    assert len(lines) == 2 and len(lines[1].split()) > 1


def test_gemini_picks_newest_flash_model():
    from marketit.llm.gemini import pick_model
    gen = ["generateContent"]
    models = [
        {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": gen},
        {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": gen},
        {"name": "models/gemini-3.8-flash-lite", "supportedGenerationMethods": gen},
        {"name": "models/gemini-3.9-flash-preview", "supportedGenerationMethods": gen},
        {"name": "models/gemini-3.8-pro", "supportedGenerationMethods": gen},
        {"name": "models/text-embedding-9", "supportedGenerationMethods": ["embedContent"]},
    ]
    assert pick_model(models) == "gemini-3.8-flash"


def test_gemini_switches_model_when_retired(isolated, monkeypatch):
    from .conftest import FakeResponse
    from marketit.llm.gemini import GeminiLLM
    monkeypatch.setenv("GEMINI_API_KEY", "k" * 20)
    GeminiLLM._resolved.clear()
    web = isolated
    base = "https://generativelanguage.googleapis.com/v1beta/models"
    web.on("POST", f"{base}/gemini-old:generateContent", FakeResponse(404, text="model retired"))
    web.on("GET", base, {"models": [{"name": "models/gemini-9-flash", "supportedGenerationMethods": ["generateContent"]}]})
    web.on("POST", f"{base}/gemini-9-flash:generateContent", {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]})
    assert GeminiLLM("gemini-old").complete("x") == "hi"
    assert GeminiLLM("gemini-old").complete("y") == "hi"
    assert len(web.calls_to(f"{base}/gemini-old")) == 1   # remembered, not retried
