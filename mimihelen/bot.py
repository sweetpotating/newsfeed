"""Interactive long-polling bot (the ``serve`` mode).

Keeps a small process alive, long-polls Telegram for messages and button
presses, and responds. This is what makes Mimi Helen feel like a companion
rather than a one-way alarm: Helen can log a dose, check today's progress, see
her streak, and pull an eye-care tip whenever she likes.

Commands:
  /start     greet &amp; show what the bot can do
  /done      log an eyedrop dose now
  /today     show today's progress vs the daily goal
  /streak    show the current daily-goal streak
  /tip       a random eye-care tip
  /schedule  show the configured reminder times
  /help      list commands
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

from . import content
from .config import Config
from .schedule import now_in_tz
from .telegram import TelegramClient, reminder_keyboard
from .tracker import DoseTracker

log = logging.getLogger("mimihelen.bot")

COMMANDS = [
    {"command": "done", "description": "done my drops liao"},
    {"command": "today", "description": "how many drops today"},
    {"command": "streak", "description": "my streak"},
    {"command": "tip", "description": "give me an eye-care tip"},
    {"command": "schedule", "description": "when are my reminders"},
    {"command": "help", "description": "what is this bot"},
]


def _seed(now: datetime, extra: str = "") -> str:
    return now.strftime("%Y-%m-%d") + "|" + extra


def progress_text(cfg: Config, tracker: DoseTracker, now: datetime) -> str:
    today = now.date()
    n = tracker.doses_on(today)
    goal = cfg.daily_goal
    filled = "💧" * min(n, goal)
    empty = "○" * max(0, goal - n)
    bar = filled + empty
    line = f"📊 today: {n}/{goal} drops  {bar}"
    times = tracker.times_on(today)
    if times:
        line += "\n🕒 you did them at: " + ", ".join(times)
    if n >= goal:
        line += "\n\nok good. goal hit for today 👌🏼 proud of you 🤍"
    else:
        line += f"\n\n{goal - n} more to go. don't 半途而废 ah 💪🏻"
    return line


def help_text(cfg: Config) -> str:
    return (
        f"hi {cfg.friend_name} 👋 it's me, dr helen (well, the bot version).\n\n"
        "my job is simple: make sure you do your eyedrops through the day, "
        "stop you from <b>rubbing your eyes</b> (i'm serious), and nag you to "
        "take care of your eyes properly.\n\n"
        "<b>what you can do:</b>\n"
        "• /done — i did my drops ✅\n"
        "• /today — how many drops today 📊\n"
        "• /streak — my streak 🔥\n"
        "• /tip — give me an eye-care tip 💡\n"
        "• /schedule — when are my reminders 🕒\n"
        "• /help — this\n\n"
        "or just tap the buttons under any reminder lah. don't shy. 💧"
    )


class MimiHelenBot:
    """Stateful handler for one chat (the friend's chat)."""

    def __init__(self, cfg: Config, client: TelegramClient, tracker: DoseTracker):
        self.cfg = cfg
        self.client = client
        self.tracker = tracker

    # ---- individual actions -------------------------------------------
    def _log_dose(self, chat_id: str, now: datetime) -> str:
        count = self.tracker.log_dose(now)
        self.tracker.save()
        msg = f"ok noted. that's {count}/{self.cfg.daily_goal} today 👌🏼"
        if count == self.cfg.daily_goal:
            msg += "\ngoal hit. good. now go rest 🤍"
        elif count > self.cfg.daily_goal:
            msg += "\nextra drops today ah. not bad 🧡"
        return msg

    def _streak_text(self, now: datetime) -> str:
        s = self.tracker.streak(now.date())
        if s <= 0:
            return "no streak yet leh. do today's drops and start one 💪🏻"
        day_word = "day" if s == 1 else "days"
        return (f"🔥 <b>{s} {day_word}</b> in a row you hit your goal. "
                "ok consistent. don't 半途而废 ah.")

    def _schedule_text(self) -> str:
        times = ", ".join(self.cfg.times)
        return (
            f"🕒 your reminders ({self.cfg.tz}):\n{times}\n\n"
            f"🎯 goal: {self.cfg.daily_goal} drops a day. don't bluff me ah."
        )

    # ---- update dispatch ----------------------------------------------
    def handle_message(self, message: dict) -> None:
        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))
        text = (message.get("text") or "").strip()
        if not chat_id or not text:
            return
        now = now_in_tz(self.cfg.tz)
        # Normalise "/done@MimiHelenBot args" -> "done".
        cmd = text.split()[0].lstrip("/").split("@")[0].lower()

        if cmd in ("start", "help"):
            self.client.send_message(help_text(self.cfg), chat_id=chat_id,
                                     reply_markup=reminder_keyboard())
        elif cmd in ("done", "drop", "drops", "log"):
            self.client.send_message(self._log_dose(chat_id, now), chat_id=chat_id)
        elif cmd == "today":
            self.client.send_message(
                progress_text(self.cfg, self.tracker, now), chat_id=chat_id)
        elif cmd == "streak":
            self.client.send_message(self._streak_text(now), chat_id=chat_id)
        elif cmd in ("tip", "tips"):
            self.client.send_message(
                content.eye_care_tip(_seed(now, "ondemand" + str(time.time()))),
                chat_id=chat_id)
        elif cmd == "schedule":
            self.client.send_message(self._schedule_text(), chat_id=chat_id)
        else:
            self.client.send_message(
                "huh? i don't understand. /help to see what i can do lah.",
                chat_id=chat_id)

    def handle_callback(self, callback: dict) -> None:
        data = callback.get("data", "")
        cb_id = callback.get("id", "")
        message = callback.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        now = now_in_tz(self.cfg.tz)

        if data == "done":
            count = self.tracker.log_dose(now)
            self.tracker.save()
            self.client.answer_callback_query(
                cb_id, f"noted ({count}/{self.cfg.daily_goal} today) 👌🏼")
            self.client.send_message(
                progress_text(self.cfg, self.tracker, now), chat_id=chat_id)
        elif data == "snooze":
            self.client.answer_callback_query(cb_id, "ok, 15 min. don't run away ah ⏰")
            self._snooze(chat_id, now)
        elif data == "today":
            self.client.answer_callback_query(cb_id)
            self.client.send_message(
                progress_text(self.cfg, self.tracker, now), chat_id=chat_id)
        elif data == "tip":
            self.client.answer_callback_query(cb_id)
            self.client.send_message(
                content.eye_care_tip(_seed(now, "cb" + str(time.time()))),
                chat_id=chat_id)
        else:
            self.client.answer_callback_query(cb_id)

    def _snooze(self, chat_id: str, now: datetime, delay_sec: int = 15 * 60) -> None:
        # Simple in-process snooze. For long-lived serve mode this is fine; we
        # sleep without blocking other chats only because there is a single
        # user, keeping the bot intentionally tiny.
        time.sleep(delay_sec)
        seed = _seed(now, "snooze")
        self.client.send_message(
            "⏰ ok time's up ah — " + content.build_reminder(self.cfg.friend_name, seed),
            chat_id=chat_id, reply_markup=reminder_keyboard())


def serve(cfg: Config) -> int:
    """Run the long-polling loop until interrupted."""
    cfg.require_telegram()
    client = TelegramClient(cfg.bot_token, cfg.chat_id, timeout=cfg.timeout)
    tracker = DoseTracker(cfg.state_file, daily_goal=cfg.daily_goal)
    handler = MimiHelenBot(cfg, client, tracker)

    try:
        client.set_my_commands(COMMANDS)
    except RuntimeError as exc:
        log.warning("Could not set command menu: %s", exc)

    log.info("Mimi Helen Bot is now serving (long-poll). Ctrl-C to stop.")
    offset: Optional[int] = None
    while True:
        try:
            updates = client.get_updates(offset, cfg.poll_timeout)
        except (RuntimeError, Exception) as exc:  # network blips shouldn't kill it
            log.warning("getUpdates failed: %s; retrying in 3s", exc)
            time.sleep(3)
            continue
        for upd in updates:
            offset = upd["update_id"] + 1
            try:
                if "message" in upd:
                    handler.handle_message(upd["message"])
                elif "callback_query" in upd:
                    handler.handle_callback(upd["callback_query"])
            except RuntimeError as exc:
                log.warning("Failed handling update %s: %s", upd.get("update_id"), exc)
