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
import os
import subprocess
import time
from datetime import datetime, timedelta
from typing import List, Optional

from . import content, qa, report
from .config import Config, parse_time_list
from .schedule import current_slot, due_slots, now_in_tz
from .telegram import TelegramClient, reminder_keyboard, undo_keyboard
from .tracker import DoseTracker

log = logging.getLogger("mimihelen.bot")

COMMANDS = [
    {"command": "done", "description": "done my drops liao"},
    {"command": "undo", "description": "oops, un-log my last drop"},
    {"command": "today", "description": "how many drops today"},
    {"command": "streak", "description": "my streak"},
    {"command": "report", "description": "compliance report to forward to dr helen"},
    {"command": "tip", "description": "give me an eye-care tip"},
    {"command": "test", "description": "send me a test reminder now"},
    {"command": "schedule", "description": "see / change reminder times"},
    {"command": "snooze", "description": "see / change snooze length"},
    {"command": "ask", "description": "ask me anything about your eyes/drops"},
    {"command": "help", "description": "what is this bot"},
]



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
        "• /undo — oops, un-log that drop ↩️\n"
        "• /today — how many drops today 📊\n"
        "• /streak — my streak 🔥\n"
        "• /report — compliance report to forward to dr helen 📋\n"
        "• /tip — give me an eye-care tip 💡\n"
        "• /test — send a test reminder now (to try the buttons) 🧪\n"
        "• /schedule — see or change your reminder times 🕒\n"
        "• /snooze — see or change the snooze length ⏰\n"
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
        # Walks the day's shuffled tip order so on-demand /tip doesn't repeat.
        self._tip_day: str = ""
        self._tip_pos: int = 0
        # Pending snooze countdowns: each is {chat_id, fire_at, msg_id, last}.
        self._pending: List[dict] = []

    def _kb(self) -> dict:
        """Reminder buttons with the snooze label matching the configured delay."""
        return reminder_keyboard(self.cfg.snooze_min)

    def _next_tip(self, now: datetime) -> str:
        """Next on-demand tip, cycling the day's order without repeats."""
        day = now.strftime("%Y-%m-%d")
        if day != self._tip_day:
            self._tip_day, self._tip_pos = day, 0
        tip = content.tip_for_slot(day, self._tip_pos)
        self._tip_pos += 1
        return tip

    # ---- state persistence --------------------------------------------
    def _save(self) -> None:
        """Save tracker state, and (in CI) commit it back so it survives restarts."""
        self.tracker.save()
        if os.environ.get("MIMIHELEN_GIT_PERSIST", "").strip().lower() not in (
            "1", "true", "yes", "on"
        ):
            return
        path = self.cfg.state_file
        try:
            subprocess.run(["git", "add", path], check=True, capture_output=True)
            if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
                return  # nothing changed
            subprocess.run(
                ["git", "-c", "user.name=mimihelen-bot",
                 "-c", "user.email=mimihelen-bot@users.noreply.github.com",
                 "commit", "-m", "chore: update Mimi Helen state"],
                check=True, capture_output=True)
            for _ in range(4):
                if subprocess.run(["git", "push"], capture_output=True).returncode == 0:
                    return
                subprocess.run(["git", "pull", "--rebase", "--autostash"],
                               capture_output=True)
            log.warning("Could not push state after retries.")
        except Exception as exc:  # persistence is best-effort, never crash
            log.warning("git persist failed: %s", exc)

    # ---- individual actions -------------------------------------------
    def _log_dose(self, chat_id: str, now: datetime) -> str:
        count = self.tracker.log_dose(now)
        self._save()
        msg = f"ok noted. that's {count}/{self.cfg.daily_goal} today 👌🏼"
        if count == self.cfg.daily_goal:
            msg += "\ngoal hit. good. now go rest 🤍"
        elif count > self.cfg.daily_goal:
            msg += "\nextra drops today ah. not bad 🧡"
        return msg

    def _undo_dose(self, now: datetime) -> str:
        """Remove the last-logged dose today (for an accidental Done)."""
        remaining = self.tracker.undo_dose(now.date())
        if remaining is None:
            return "nothing to undo lah — you haven't logged any drops today."
        self._save()
        return f"ok, undone. back to {remaining}/{self.cfg.daily_goal} today. butterfingers ah 🙄"

    def _set_snooze(self, raw: str) -> str:
        """Show or change how long the ⏰ Snooze button waits."""
        raw = (raw or "").strip().lower().replace("min", "").replace("m", "").strip()
        if not raw:
            return (f"⏰ snooze is <b>{self.cfg.snooze_min} min</b> now.\n"
                    "to change: <code>/snooze 10</code> (1–180 min).\n\n"
                    "to actually snooze a reminder, tap the <b>⏰ Snooze</b> button "
                    "on the reminder itself — i'll buzz you again after.")
        try:
            mins = int(raw)
        except ValueError:
            return "give me a number lah, like <code>/snooze 5</code>."
        if not 1 <= mins <= 180:
            return "pick between 1 and 180 min. don't play."
        self.cfg.snooze_min = mins
        self.tracker.set_schedule(snooze_min=mins)
        self._save()
        return f"ok ✅ snooze is now <b>{mins} min</b>. the button will say so on the next reminder."

    def _change_schedule(self, raw: str) -> str:
        """Set new reminder times (and optional goal) from a chat command."""
        times = parse_time_list(raw)
        if not times:
            return (
                "give me the times lah, like:\n"
                "<code>/schedule 08:00, 13:00, 19:00, 22:00</code>\n\n"
                "(24-hour, comma-separated. i'll take it from there.)"
            )
        if len(times) > 12:
            return "12 reminders a day is more than enough lah. give me fewer."
        self.cfg.times = times
        self.tracker.set_schedule(times=times)
        self.tracker.set_schedule(daily_goal=len(times))
        self.cfg.daily_goal = len(times)
        self._save()
        return (
            "ok done ✅ new schedule:\n"
            f"🕒 {', '.join(times)} ({self.cfg.tz})\n"
            f"🎯 goal: {len(times)} drops a day.\n\n"
            "takes effect from the next reminder. don't bluff me ah 😤"
        )

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
            f"🎯 goal: {self.cfg.daily_goal} drops a day.\n\n"
            "want to change? send e.g.\n"
            "<code>/schedule 08:00, 13:00, 19:00, 22:00</code>"
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
            # No action buttons here — snooze etc. belong on actual reminders.
            self.client.send_message(help_text(self.cfg), chat_id=chat_id)
        elif cmd in ("test", "testreminder", "remindme", "remind"):
            # A sample reminder right now, with the buttons (incl. ⏰ Snooze).
            seed = now.strftime("%Y-%m-%d") + "|test"
            self.client.send_message(
                content.build_reminder(self.cfg.friend_name, seed),
                chat_id=chat_id, reply_markup=self._kb())
        elif cmd in ("done", "drop", "drops", "log"):
            self.client.send_message(self._log_dose(chat_id, now), chat_id=chat_id,
                                     reply_markup=undo_keyboard())
        elif cmd in ("undo", "undrop", "oops"):
            self.client.send_message(self._undo_dose(now), chat_id=chat_id)
        elif cmd == "today":
            self.client.send_message(
                progress_text(self.cfg, self.tracker, now), chat_id=chat_id)
        elif cmd == "streak":
            self.client.send_message(self._streak_text(now), chat_id=chat_id)
        elif cmd in ("tip", "tips"):
            self.client.send_message(
                self._next_tip(now),
                chat_id=chat_id)
        elif cmd in ("schedule", "times", "reschedule"):
            # "/schedule 08:00,13:00,..." changes it; bare "/schedule" shows it.
            rest = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
            if rest.strip():
                self.client.send_message(self._change_schedule(rest), chat_id=chat_id)
            else:
                self.client.send_message(self._schedule_text(), chat_id=chat_id)
        elif cmd == "snooze":
            # "/snooze 10" sets the snooze length; bare "/snooze" shows it.
            rest = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
            self.client.send_message(self._set_snooze(rest), chat_id=chat_id)
        elif cmd in ("report", "compliance"):
            # "/report" = last 7 days; "/report 14" = last 14. Forwardable to the doctor.
            arg = text.split(None, 1)[1].strip() if len(text.split(None, 1)) > 1 else ""
            try:
                days = int(arg) if arg else 7
            except ValueError:
                days = 7
            self.client.send_message(
                report.build_report(self.cfg, self.tracker, now, days),
                chat_id=chat_id)
            self.client.send_message(
                "👆 forward that to dr helen to show your eyedrop compliance ah. "
                "(tip: <code>/report 14</code> or <code>/report 30</code> for a longer period.)",
                chat_id=chat_id)
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
            self._save()
            self.client.answer_callback_query(
                cb_id, f"noted ({count}/{self.cfg.daily_goal} today) 👌🏼")
            # Offer an undo in case it was a mis-tap.
            self.client.send_message(
                progress_text(self.cfg, self.tracker, now), chat_id=chat_id,
                reply_markup=undo_keyboard())
        elif data == "undo":
            remaining = self.tracker.undo_dose(now.date())
            if remaining is None:
                self.client.answer_callback_query(cb_id, "nothing to undo")
            else:
                self._save()
                self.client.answer_callback_query(
                    cb_id, f"undone ({remaining}/{self.cfg.daily_goal} today) ↩️")
                self.client.send_message(
                    progress_text(self.cfg, self.tracker, now), chat_id=chat_id)
        elif data == "snooze":
            if self.has_pending():
                rem = self._pending_remaining(now)
                self.client.answer_callback_query(
                    cb_id, f"already snoozing — {rem} left ah ⏰")
            else:
                self._start_snooze(chat_id, now)
                self.client.answer_callback_query(
                    cb_id, f"ok, {self.cfg.snooze_min} min ⏰")
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
        """Send every reminder that's due now and not yet sent. Returns True if
        anything was sent.

        Lets a single long-running ``serve`` process do everything — reminders,
        buttons and Q&A. Fires AT the scheduled time (never early), catching up
        anything missed during a restart (within ``slot_tolerance_min``).
        Sending *all* due-unsent slots means closely-spaced reminders can't slip
        between poll cycles; ``sent_slots`` keeps each to exactly one send.
        """
        day = now.strftime("%Y-%m-%d")
        sent_any = False
        for slot in due_slots(self.cfg.times, now, self.cfg.slot_tolerance_min):
            key = f"{day}|{slot.time_str}"
            if self.tracker.reminder_sent(key):
                continue
            text = content.build_reminder(
                self.cfg.friend_name, key,
                dose_label=slot.dose_label, include_howto=slot.is_first,
                tip_index=slot.index,
            )
            try:
                self.client.send_message(text, chat_id=self.cfg.chat_id,
                                         reply_markup=self._kb())
            except RuntimeError as exc:
                log.warning("Scheduled reminder failed (%s); retry next cycle.", exc)
                continue
            self.tracker.mark_reminder_sent(key)
            self.tracker.note_reminder(now)
            log.info("Sent scheduled reminder (%s).", slot.time_str)
            sent_any = True
        if sent_any:
            self.tracker.prune(now.date())
            self._save()
        return sent_any

    # ---- snooze (non-blocking, with a live countdown) -----------------
    def load_pending(self) -> None:
        """Restore snoozes persisted before a restart so they still fire."""
        self._pending = []
        for p in self.tracker.get_pending_snoozes():
            try:
                fire_at = datetime.fromisoformat(p["fire_at"])
            except (KeyError, ValueError):
                continue
            self._pending.append({"chat_id": str(p.get("chat_id", self.cfg.chat_id)),
                                  "fire_at": fire_at, "msg_id": None, "last": ""})

    def _persist_pending(self) -> None:
        self.tracker.set_pending_snoozes(
            [{"chat_id": p["chat_id"], "fire_at": p["fire_at"].isoformat()}
             for p in self._pending])
        self._save()

    def _start_snooze(self, chat_id: str, now: datetime) -> bool:
        """Begin a snooze: post a countdown message that ticks down, then
        re-sends the reminder when it hits zero. Never blocks the bot.

        Only one snooze may run at a time — returns False (and does nothing) if
        one is already active.
        """
        if self._pending:
            return False
        mins = self.cfg.snooze_min
        fire_at = now + timedelta(minutes=mins)
        resp = self.client.send_message(
            f"⏳ snoozing… <b>{mins}:00</b> left — i'll buzz you again ah.",
            chat_id=chat_id)
        msg_id = (resp or {}).get("result", {}).get("message_id")
        self._pending.append({"chat_id": chat_id, "fire_at": fire_at,
                              "msg_id": msg_id, "last": ""})
        self._persist_pending()  # survive a restart during the countdown
        return True

    def has_pending(self) -> bool:
        return bool(self._pending)

    def _pending_remaining(self, now: datetime) -> str:
        """'M:SS' left on the active snooze (or '0:00' if none)."""
        if not self._pending:
            return "0:00"
        remaining = max(0, int((self._pending[0]["fire_at"] - now).total_seconds()))
        mm, ss = divmod(remaining, 60)
        return f"{mm}:{ss:02d}"

    def process_pending(self, now: datetime) -> None:
        """Tick every snooze countdown; fire the ones that reached zero."""
        still: List[dict] = []
        fired = False
        for p in self._pending:
            remaining = (p["fire_at"] - now).total_seconds()
            if remaining <= 0:
                fired = True
                if p.get("msg_id"):
                    try:
                        self.client.edit_message_text(
                            p["chat_id"], p["msg_id"], "⏰ time's up! drops now 💧")
                    except RuntimeError:
                        pass
                seed = now.strftime("%Y-%m-%d") + "|snooze"
                try:
                    self.client.send_message(
                        "⏰ snooze over — "
                        + content.build_reminder(self.cfg.friend_name, seed),
                        chat_id=p["chat_id"], reply_markup=self._kb())
                except RuntimeError as exc:
                    log.warning("Snooze re-reminder failed: %s", exc)
                continue  # drop the entry
            mm, ss = divmod(int(remaining), 60)
            text = f"⏳ snoozing… <b>{mm}:{ss:02d}</b> left — i'll buzz you again ah."
            if p.get("msg_id") and text != p.get("last"):
                try:
                    self.client.edit_message_text(p["chat_id"], p["msg_id"], text)
                    p["last"] = text
                except RuntimeError:
                    pass
            still.append(p)
        self._pending = still
        if fired:
            self._persist_pending()  # remove fired ones from saved state


def serve(cfg: Config, schedule_enabled: bool = True) -> int:
    """Run the long-polling loop until interrupted.

    With ``schedule_enabled`` (default), a single ``serve`` process is a complete
    deployment: it sends the scheduled reminders itself AND handles buttons /
    commands / questions. Pass ``schedule_enabled=False`` (``serve --no-schedule``)
    when a separate cron already sends the reminders and you only want this
    process for the interactive bits — so reminders aren't sent twice.
    """
    cfg.require_telegram()
    tracker = DoseTracker(cfg.state_file, daily_goal=cfg.daily_goal)
    # Honour a schedule the user set from chat (persisted in state).
    cfg.apply_state_overrides(tracker)
    tracker.daily_goal = max(1, cfg.daily_goal)
    client = TelegramClient(cfg.bot_token, cfg.chat_id, timeout=cfg.timeout)
    handler = MimiHelenBot(cfg, client, tracker)
    handler.load_pending()  # resume any snooze that was mid-countdown before a restart

    try:
        client.set_my_commands(COMMANDS)
    except RuntimeError as exc:
        log.warning("Could not set command menu: %s", exc)

    mode = "reminders + buttons + Q&A" if schedule_enabled else "buttons + Q&A only"
    log.info("Mimi Helen Bot is now serving (%s). Ctrl-C to stop.", mode)
    offset: Optional[int] = None
    while True:
        nowtz = now_in_tz(cfg.tz)
        # Fire any scheduled reminder that's due (runs every poll cycle, ≤~1min).
        if schedule_enabled:
            try:
                handler.tick(nowtz)
            except Exception as exc:  # scheduling must never kill the loop
                log.warning("Scheduler tick failed: %s", exc)
        # Tick any live snooze countdowns.
        try:
            handler.process_pending(nowtz)
        except Exception as exc:
            log.warning("Snooze processing failed: %s", exc)

        # Poll quickly while a countdown is ticking so it stays live; otherwise
        # use the long poll to stay efficient.
        poll = 10 if handler.has_pending() else cfg.poll_timeout
        try:
            updates = client.get_updates(offset, poll)
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
