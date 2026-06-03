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


def parse_time_list(raw: str) -> List[str]:
    """Parse "8:00, 12:30; 20:5" -> ["08:00", "12:30", "20:05"].

    Drops anything that isn't a valid 24h HH:MM, de-duplicates, and sorts. Used
    both for env config and for the in-chat "change schedule" command.
    """
    out: List[str] = []
    for chunk in (raw or "").replace(";", ",").replace(" ", ",").split(","):
        t = chunk.strip()
        if not t:
            continue
        try:
            hh, mm = t.split(":")
            hh, mm = int(hh), int(mm)
        except ValueError:
            continue
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            out.append(f"{hh:02d}:{mm:02d}")
    # De-dupe preserving order, then sort by time of day.
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return sorted(uniq, key=lambda s: (int(s[:2]), int(s[3:])))


def _times(name: str, default: List[str]) -> List[str]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return list(default)
    return parse_time_list(raw) or list(default)


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
    # Minutes the "⏰ Snooze" button waits before re-sending the reminder.
    snooze_min: int = 5
    # When `remind` runs from cron a few minutes late, still treat it as the
    # nearest slot within this many minutes.
    slot_tolerance_min: int = 30

    # Tracker (doses + streak) state file, committed back by the Action.
    state_file: str = "state/mimihelen.json"

    # serve mode: seconds to long-poll getUpdates.
    poll_timeout: int = 50

    # ---- Q&A (serve mode only) ----------------------------------------
    # A free-text description of the drops she's actually on, so the bot can
    # answer "what eyedrops am i using / how does it help" accurately. Set this
    # to whatever her eye doctor prescribed, e.g.
    #   "lubricating drops (artificial tears) for dry eyes, + a steroid drop."
    eyedrops: str = ""
    # Optional LLM fallback for open-ended questions. If the key is unset, the
    # bot still answers the built-in questions; it just won't free-talk.
    anthropic_api_key: str = ""
    qa_model: str = "claude-haiku-4-5"

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
            snooze_min=max(1, _int("MIMIHELEN_SNOOZE_MIN", 5)),
            slot_tolerance_min=_int("MIMIHELEN_SLOT_TOLERANCE_MIN", 30),
            state_file=os.environ.get("MIMIHELEN_STATE_FILE", "state/mimihelen.json").strip()
            or "state/mimihelen.json",
            poll_timeout=_int("MIMIHELEN_POLL_TIMEOUT", 50),
            eyedrops=os.environ.get("MIMIHELEN_EYEDROPS", "").strip(),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
            qa_model=os.environ.get("MIMIHELEN_QA_MODEL", "claude-haiku-4-5").strip()
            or "claude-haiku-4-5",
        )

    def apply_state_overrides(self, tracker) -> None:
        """Override the schedule with values set from chat (persisted in state)."""
        times = tracker.get_times()
        if times:
            self.times = list(times)
        goal = tracker.get_daily_goal()
        if goal:
            self.daily_goal = goal
        snooze = tracker.get_snooze_min()
        if snooze:
            self.snooze_min = snooze

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
