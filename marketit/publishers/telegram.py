"""Telegram channel via a bot. Secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (e.g. @mychannel).

Make the bot (from @BotFather) an admin of your channel so it can post.
"""

from __future__ import annotations

from .. import http
from ..config import env
from .base import Publisher, PublishError


class Telegram(Publisher):
    name = "telegram"
    label = "Telegram"
    max_chars = 1024  # caption limit when posting a photo
    hashtags = "0-2 hashtags"
    audience = "your own channel's subscribers only (does not find new people)"
    style_notes = "Like a message to fans: news-style, can be a little longer."
    secrets = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
    max_image_bytes = 9_000_000

    def publish(self, post, image_path, image_url):
        api = f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}"
        chat = env("TELEGRAM_CHAT_ID")
        try:
            if image_path:
                resp = http.post(
                    f"{api}/sendPhoto",
                    data={"chat_id": chat, "caption": post["text"][:1024]},
                    files={"photo": (image_path.name, image_path.read_bytes(), "image/jpeg")},
                ).json()
            else:
                resp = http.post(f"{api}/sendMessage", data={"chat_id": chat, "text": post["text"]}).json()
        except http.HTTPError as exc:
            # Never let the bot token (it's in the URL) end up in logs or issue comments.
            raise PublishError(str(exc).replace(env("TELEGRAM_BOT_TOKEN"), "***"), permanent=exc.status in (401, 403)) from None
        msg_id = resp["result"]["message_id"]
        url = f"https://t.me/{chat.lstrip('@')}/{msg_id}" if chat.startswith("@") else None
        return {"id": str(msg_id), "url": url}
