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

from . import content, qa
from .config import Config
from .schedule import current_slot, now_in_tz
from .telegram import TelegramClient, reminder_keyboard
from .tracker import DoseTracker

log = logging.getLogger("mimihelen.bot")

COMMANDS = [
    {"command": "done", "description": "done my drops liao"},
    {"command": "today", "description": "how many drops today"},
    {"command": "streak", "description": "my streak"},
    {"command": "tip", "description": "give me an eye-care tip"},
    {"command": "schedule", "description": "when are my reminders"},
    {"command": "ask", "description": "ask me anything about your eyes/drops"},
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
        "or just <b>ask me anything</b> — \"when's my next reminder?\", "
        "\"what are my eyedrops for?\", \"how do i use the drops?\". "
        "no need command, just type. 💧"
    )


class MimiHelenBot:
    """Stateful handler for one chat (the friend's chat)."""

    def __init__(self, cfg: Config, client: TelegramClient, tracker: DoseTracker):
        self.cfg = cfg
        self.client = client
        self.tracker = tracker
        # Slots already fired this run, as "YYYY-MM-DD|HH:MM", so the internal
        # scheduler sends each reminder at most once.
        self._sent_slots: set[str] = set()
        # Walks the day's shuffled tip order so on-demand /tip doesn't repeat.
        self._tip_day: str = ""
        self._tip_pos: int = 0

    def _next_tip(self, now: datetime) -> str:
        """Next on-demand tip, cycling the day's order without repeats."""
        day = now.strftime("%Y-%m-%d")
        if day != self._tip_day:
            self._tip_day, self._tip_pos = day, 0
        tip = content.tip_for_slot(day, self._tip_pos)
        self._tip_pos += 1
        return tip

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
                self._next_tip(now),
                chat_id=chat_id)
        elif cmd == "schedule":
            self.client.send_message(self._schedule_text(), chat_id=chat_id)
        elif cmd in ("ask", "question", "q"):
            # Explicit "/ask <question>" — answer the rest of the text.
            q = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
            self.client.send_message(
                qa.answer(q or "what can you help with", self.cfg, self.tracker, now),
                chat_id=chat_id)
        else:
            # Anything else is treated as a free-text question.
            self.client.send_message(
                qa.answer(text, self.cfg, self.tracker, now), chat_id=chat_id)

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
                self._next_tip(now),
                chat_id=chat_id)
        else:
            self.client.answer_callback_query(cb_id)

    # ---- internal scheduler -------------------------------------------
    def tick(self, now: datetime) -> bool:
        """Send the reminder due now, if any, exactly once. Returns True if sent.

        Lets a single long-running ``serve`` process do everything — reminders,
        buttons and Q&A — so you don't need the GitHub Actions cron at all (and
        the reminder buttons actually work, because this same process is the one
        listening for the presses).
        """
        slot = current_slot(self.cfg.times, now, self.cfg.slot_tolerance_min)
        if slot is None:
            return False
        day = now.strftime("%Y-%m-%d")
        key = f"{day}|{slot.time_str}"
        if key in self._sent_slots:
            return False
        # Only keep today's keys so the set never grows without bound.
        self._sent_slots = {k for k in self._sent_slots if k.startswith(day)}
        self._sent_slots.add(key)

        text = content.build_reminder(
            self.cfg.friend_name, key,
            dose_label=slot.dose_label, include_howto=slot.is_first,
            tip_index=slot.index,
        )
        try:
            self.client.send_message(text, chat_id=self.cfg.chat_id,
                                     reply_markup=reminder_keyboard())
            self.tracker.note_reminder(now)
            self.tracker.prune(now.date())
            self.tracker.save()
            log.info("Sent scheduled reminder (%s).", slot.time_str)
            return True
        except RuntimeError as exc:
            log.warning("Scheduled reminder failed (%s); will retry next slot.", exc)
            self._sent_slots.discard(key)
            return False

    def _snooze(self, chat_id: str, now: datetime, delay_sec: int = 15 * 60) -> None:
        # Simple in-process snooze. For long-lived serve mode this is fine; we
        # sleep without blocking other chats only because there is a single
        # user, keeping the bot intentionally tiny.
        time.sleep(delay_sec)
        seed = _seed(now, "snooze")
        self.client.send_message(
            "⏰ ok time's up ah — " + content.build_reminder(self.cfg.friend_name, seed),
            chat_id=chat_id, reply_markup=reminder_keyboard())


def serve(cfg: Config, schedule_enabled: bool = True) -> int:
    """Run the long-polling loop until interrupted.

    With ``schedule_enabled`` (default), a single ``serve`` process is a complete
    deployment: it sends the scheduled reminders itself AND handles buttons /
    commands / questions. Pass ``schedule_enabled=False`` (``serve --no-schedule``)
    when a separate cron already sends the reminders and you only want this
    process for the interactive bits — so reminders aren't sent twice.
    """
    cfg.require_telegram()
    client = TelegramClient(cfg.bot_token, cfg.chat_id, timeout=cfg.timeout)
    tracker = DoseTracker(cfg.state_file, daily_goal=cfg.daily_goal)
    handler = MimiHelenBot(cfg, client, tracker)

    try:
        client.set_my_commands(COMMANDS)
    except RuntimeError as exc:
        log.warning("Could not set command menu: %s", exc)

    mode = "reminders + buttons + Q&A" if schedule_enabled else "buttons + Q&A only"
    log.info("Mimi Helen Bot is now serving (%s). Ctrl-C to stop.", mode)
    offset: Optional[int] = None
    while True:
        # Fire any scheduled reminder that's due (runs every poll cycle, ≤~1min).
        if schedule_enabled:
            try:
                handler.tick(now_in_tz(cfg.tz))
            except Exception as exc:  # scheduling must never kill the loop
                log.warning("Scheduler tick failed: %s", exc)

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
