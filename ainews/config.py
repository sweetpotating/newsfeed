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


@dataclass
class Config:
    bot_token: str = ""
    chat_id: str = ""
    lookback_hours: int = 24
    max_items: int = 45
    max_per_feed: int = 8
    timeout: int = 20
    state_file: str = "state/seen.json"
    state_ttl_days: int = 45

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
            chat_id=os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
            lookback_hours=_int("AINEWS_LOOKBACK_HOURS", 24),
            max_items=_int("AINEWS_MAX_ITEMS", 45),
            max_per_feed=_int("AINEWS_MAX_PER_FEED", 8),
            timeout=_int("AINEWS_TIMEOUT", 20),
            state_file=os.environ.get("AINEWS_STATE_FILE", "state/seen.json").strip()
            or "state/seen.json",
            state_ttl_days=_int("AINEWS_STATE_TTL_DAYS", 45),
        )

    def require_telegram(self) -> None:
        missing = []
        if not self.bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.chat_id:
            missing.append("TELEGRAM_CHAT_ID")
        if missing:
            raise RuntimeError(
                "Missing required environment variable(s): "
                + ", ".join(missing)
                + ". Set them (or use --dry-run to preview without sending)."
            )
