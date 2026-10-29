import io
import json

import pytest
from PIL import Image

from marketit import http

SECRET_VARS = [
    "GEMINI_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY", "OLLAMA_HOST", "GITHUB_TOKEN", "GITHUB_REPOSITORY",
    "BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD", "MASTODON_BASE_URL", "MASTODON_ACCESS_TOKEN",
    "PINTEREST_ACCESS_TOKEN", "PINTEREST_BOARD_ID", "THREADS_USER_ID", "THREADS_ACCESS_TOKEN",
    "INSTAGRAM_USER_ID", "INSTAGRAM_ACCESS_TOKEN", "FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_TOKEN",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL",
    "X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET", "MARKETIT_NOW", "MARKETIT_REPO_PUBLIC",
]


class FakeResponse:
    def __init__(self, status=200, json_data=None, text=None, content=None):
        self.status_code = status
        self._json = json_data
        self.content = content if content is not None else (
            text.encode() if text is not None else json.dumps(json_data).encode()
        )
        self.text = text if text is not None else self.content.decode("utf-8", "replace")

    def json(self):
        return self._json if self._json is not None else json.loads(self.text)


class FakeWeb:
    """Routes (METHOD, url-prefix) to handlers; records every call."""

    def __init__(self):
        self.routes = []
        self.calls = []

    def on(self, method, prefix, handler):
        self.routes.insert(0, (method.upper(), prefix, handler))

    def request(self, method, url, **kwargs):
        self.calls.append((method.upper(), url, kwargs))
        for m, prefix, handler in self.routes:
            if m == method.upper() and url.startswith(prefix):
                result = handler(url, kwargs) if callable(handler) else handler
                return result if isinstance(result, FakeResponse) else FakeResponse(json_data=result)
        return FakeResponse(404, text="not found")

    def calls_to(self, prefix):
        return [c for c in self.calls if c[1].startswith(prefix)]


def png_bytes(size=(800, 600), color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    for var in SECRET_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MARKETIT_DATA", str(tmp_path / "data"))
    (tmp_path / "items").mkdir()
    import marketit.intake as intake_mod
    monkeypatch.setattr(intake_mod, "ROOT", tmp_path)
    web = FakeWeb()
    monkeypatch.setattr(http, "session", web)
    return web


@pytest.fixture
def web(isolated):
    return isolated


@pytest.fixture
def config():
    from marketit.config import load_config

    cfg = load_config()
    cfg["images"]["ai_provider"] = "none"
    return cfg


@pytest.fixture
def fake_llm():
    from marketit.llm.fake import FakeLLM
    from marketit.llm import ChainLLM

    return ChainLLM([FakeLLM()])
