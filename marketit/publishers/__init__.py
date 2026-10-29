"""Social channels. Each publisher knows its limits, whether it's set up, and how to post."""

from __future__ import annotations

from .base import Publisher, PublishError
from .bluesky import Bluesky
from .discord import Discord
from .facebook import Facebook
from .instagram import Instagram
from .mastodon import Mastodon
from .pinterest import Pinterest
from .telegram import Telegram
from .threads import Threads
from .x import X

ALL: dict[str, type[Publisher]] = {
    cls.name: cls
    for cls in (Bluesky, Mastodon, Pinterest, Threads, Instagram, Facebook, Telegram, Discord, X)
}


def get_publisher(name: str, config: dict) -> Publisher:
    return ALL[name](config)


def connected_channels(config: dict) -> list[str]:
    """Channels that have their secrets set and aren't switched off in config.yaml."""
    out = []
    for name, cls in ALL.items():
        settings = config.get("channels", {}).get(name, {}) or {}
        if settings.get("enabled", True) is False:
            continue
        if cls.configured():
            out.append(name)
    return out


def channel_guide() -> str:
    """One line per channel, for prompts where the AI chooses channels."""
    return "\n".join(f"- {c.name}: {c.audience}" for c in ALL.values())


__all__ = ["ALL", "Publisher", "PublishError", "get_publisher", "connected_channels", "channel_guide"]
