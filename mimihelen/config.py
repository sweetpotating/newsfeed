"""Runtime configuration for Mimi Helen Bot, read from environment variables.

The Telegram token and chat id are required only when actually talking to
Telegram. Everything else has a friendly default so the bot runs with zero
tuning, and every knob is overridable from the environment / GitHub secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

# Sensible default: four reminders across a waking day, hitting the "3-5 times
# a day" goal. Times are HH:MM, 24-hour, in MIMIHELEN_TZ. Override with
# MIMIHELEN_TIMES="07:00,12:00,18:00,22:00".
DEFAULT_TIMES = ["07:00", "12:00", "18:00", "22:00"]
DEFAULT_TZ = "Asia/Singapore"


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


def _times(name: str, default: List[str]) -> List[str]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return list(default)
    out: List[str] = []
    for chunk in raw.replace(";", ",").split(","):
        t = chunk.strip()
        if not t:
            continue
        # Accept "8:00" or "08:00"; normalise to zero-padded HH:MM.
        try:
            hh, mm = t.split(":")
            out.append(f"{int(hh):02d}:{int(mm):02d}")
        except ValueError:
            continue
    return out or list(default)


@dataclass
class Config:
    bot_token: str = ""
    chat_id: str = ""
    timeout: int = 20

    # Who the bot is reminding (used in greetings).
    friend_name: str = "Helen"

    # Reminder schedule.
    times: List[str] = field(default_factory=lambda: list(DEFAULT_TIMES))
    tz: str = DEFAULT_TZ
    # Daily eyedrop goal (used for progress / streak). 3-5 is the target.
    daily_goal: int = 4
    # When `remind` runs from cron a few minutes late, still treat it as the
    # nearest slot within this many minutes.
    slot_tolerance_min: int = 30

    # Tracker (doses + streak) state file, committed back by the Action.
    state_file: str = "state/mimihelen.json"

    # serve mode: seconds to long-poll getUpdates.
    poll_timeout: int = 50

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
            chat_id=os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
            timeout=_int("MIMIHELEN_TIMEOUT", 20),
            friend_name=os.environ.get("MIMIHELEN_FRIEND_NAME", "Helen").strip()
            or "Helen",
            times=_times("MIMIHELEN_TIMES", DEFAULT_TIMES),
            tz=os.environ.get("MIMIHELEN_TZ", DEFAULT_TZ).strip() or DEFAULT_TZ,
            daily_goal=_int("MIMIHELEN_DAILY_GOAL", 4),
            slot_tolerance_min=_int("MIMIHELEN_SLOT_TOLERANCE_MIN", 30),
            state_file=os.environ.get("MIMIHELEN_STATE_FILE", "state/mimihelen.json").strip()
            or "state/mimihelen.json",
            poll_timeout=_int("MIMIHELEN_POLL_TIMEOUT", 50),
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
