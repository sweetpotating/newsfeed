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
    # Only surface roles (re)posted within this many hours on a normal run.
    # Jobs move slower than news, so the default window is a week.
    lookback_hours: int = 168
    max_items: int = 15                # cap messages per run so the chat stays readable
    timeout: int = 20                  # per-board network timeout (seconds)
    state_file: str = "state/jobs_seen.json"
    state_ttl_days: int = 90

    # AI "what this role is" one-liner (optional, needs an Anthropic key).
    anthropic_api_key: str = ""
    summary_model: str = "claude-haiku-4-5"
    summarize: bool = True

    # Pause between per-job messages (seconds) to respect Telegram limits.
    send_delay: float = 1.0

    # Comma-separated extra location keywords to accept beyond Singapore
    # (e.g. "remote, apac"). Empty by default — strictly Singapore.
    extra_locations: str = ""

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
            chat_id=os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
            lookback_hours=_int("AIJOBS_LOOKBACK_HOURS", 168),
            max_items=_int("AIJOBS_MAX_ITEMS", 15),
            timeout=_int("AIJOBS_TIMEOUT", 20),
            state_file=os.environ.get("AIJOBS_STATE_FILE", "state/jobs_seen.json").strip()
            or "state/jobs_seen.json",
            state_ttl_days=_int("AIJOBS_STATE_TTL_DAYS", 90),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
            summary_model=os.environ.get("AIJOBS_SUMMARY_MODEL", "claude-haiku-4-5").strip()
            or "claude-haiku-4-5",
            summarize=_bool("AIJOBS_SUMMARIZE", True),
            send_delay=float(_int("AIJOBS_SEND_DELAY_MS", 1000)) / 1000.0,
            extra_locations=os.environ.get("AIJOBS_EXTRA_LOCATIONS", "").strip(),
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
