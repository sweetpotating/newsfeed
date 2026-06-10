"""Runtime configuration, read from environment variables.

Secrets (the Telegram token and chat id) are required only when actually
sending. Everything else has a sane default so the bot can run with zero
tuning, and every knob is overridable from the environment / GitHub secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    bot_token: str = ""
    chat_id: str = ""
    lookback_hours: int = 24
    max_items: int = 10
    max_per_feed: int = 8
    timeout: int = 20
    state_file: str = "state/seen.json"
    subscriber_file: str = "state/subscribers.json"
    state_ttl_days: int = 45

    # AI summaries (top-3 takeaways).
    anthropic_api_key: str = ""
    summary_model: str = "claude-haiku-4-5"
    summarize: bool = True

    # Delivery: one Telegram message per article, image attached when available.
    photos: bool = True
    # Pause between per-article messages (seconds) to respect Telegram limits.
    send_delay: float = 1.0

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
            chat_id=os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
            lookback_hours=_int("AINEWS_LOOKBACK_HOURS", 24),
            max_items=_int("AINEWS_MAX_ITEMS", 10),
            max_per_feed=_int("AINEWS_MAX_PER_FEED", 8),
            timeout=_int("AINEWS_TIMEOUT", 20),
            state_file=os.environ.get("AINEWS_STATE_FILE", "state/seen.json").strip()
            or "state/seen.json",
            subscriber_file=os.environ.get(
                "AINEWS_SUBSCRIBER_FILE", "state/subscribers.json"
            ).strip()
            or "state/subscribers.json",
            state_ttl_days=_int("AINEWS_STATE_TTL_DAYS", 45),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
            summary_model=os.environ.get("AINEWS_SUMMARY_MODEL", "claude-haiku-4-5").strip()
            or "claude-haiku-4-5",
            summarize=_bool("AINEWS_SUMMARIZE", True),
            photos=_bool("AINEWS_PHOTOS", True),
            send_delay=float(_int("AINEWS_SEND_DELAY_MS", 1000)) / 1000.0,
        )

    def require_telegram(self) -> None:
        # The bot token is always required to talk to Telegram. A chat id is
        # optional now: delivery is driven by the subscriber list, with
        # TELEGRAM_CHAT_ID acting as an always-on extra recipient (e.g. the
        # owner's own chat or a channel) when set.
        if not self.bot_token:
            raise RuntimeError(
                "Missing required environment variable TELEGRAM_BOT_TOKEN. "
                "Set it (or use --dry-run to preview without sending)."
            )
