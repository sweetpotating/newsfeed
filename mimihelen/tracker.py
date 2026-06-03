"""Persistent dose tracking: how many drops per day, and the current streak.

A tiny JSON file maps an ISO date (YYYY-MM-DD) to the list of times a dose was
logged that day, plus a little metadata. It mirrors the ai-news dedup-state
approach: small, human-readable, and committed back to the repo by the Action
so progress survives between stateless runs.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional


class DoseTracker:
    def __init__(self, path: str, daily_goal: int = 4):
        self.path = path
        self.daily_goal = max(1, daily_goal)
        self._days: Dict[str, List[str]] = {}
        self._meta: Dict[str, object] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                days = data.get("days", {})
                if isinstance(days, dict):
                    self._days = {
                        k: list(v) for k, v in days.items() if isinstance(v, list)
                    }
                meta = data.get("meta", {})
                if isinstance(meta, dict):
                    self._meta = meta
        except (json.JSONDecodeError, ValueError, OSError):
            # Corrupt/empty state must never crash a reminder.
            self._days = {}
            self._meta = {}

    # ---- queries -------------------------------------------------------
    def doses_on(self, day: date) -> int:
        return len(self._days.get(day.isoformat(), []))

    def times_on(self, day: date) -> List[str]:
        return list(self._days.get(day.isoformat(), []))

    def goal_met(self, day: date) -> bool:
        return self.doses_on(day) >= self.daily_goal

    def streak(self, today: date) -> int:
        """Consecutive days (ending today or yesterday) that met the goal.

        Today is allowed to be still-in-progress: the streak counts back from
        today if today's goal is met, otherwise from yesterday, so an unfinished
        today doesn't reset a real streak.
        """
        start = today if self.goal_met(today) else today - timedelta(days=1)
        count = 0
        day = start
        while self.goal_met(day):
            count += 1
            day -= timedelta(days=1)
        return count

    # ---- mutations -----------------------------------------------------
    def log_dose(self, when: datetime) -> int:
        """Record a dose at ``when``; returns the day's new dose count."""
        key = when.date().isoformat()
        self._days.setdefault(key, []).append(when.strftime("%H:%M"))
        return len(self._days[key])

    def undo_dose(self, day: date) -> Optional[int]:
        """Remove the most recent dose logged on ``day`` (e.g. a mis-tap).

        Returns the day's remaining dose count, or ``None`` if there was nothing
        to undo.
        """
        key = day.isoformat()
        entries = self._days.get(key)
        if not entries:
            return None
        entries.pop()
        if not entries:
            self._days.pop(key, None)
        return len(self._days.get(key, []))

    def note_reminder(self, when: datetime) -> None:
        """Remember when the last reminder went out (for serve/snooze logic)."""
        self._meta["last_reminder"] = when.isoformat()

    @property
    def last_reminder(self) -> Optional[str]:
        val = self._meta.get("last_reminder")
        return val if isinstance(val, str) else None

    # ---- schedule overrides (set from chat, survive restarts) ----------
    def get_times(self) -> Optional[list]:
        val = self._meta.get("times")
        return list(val) if isinstance(val, list) and val else None

    def get_daily_goal(self) -> Optional[int]:
        val = self._meta.get("daily_goal")
        return int(val) if isinstance(val, int) and val > 0 else None

    def get_snooze_min(self) -> Optional[int]:
        val = self._meta.get("snooze_min")
        return int(val) if isinstance(val, int) and val > 0 else None

    def set_schedule(self, times: Optional[list] = None,
                     daily_goal: Optional[int] = None,
                     snooze_min: Optional[int] = None) -> None:
        if times is not None:
            self._meta["times"] = list(times)
        if daily_goal is not None:
            self._meta["daily_goal"] = int(daily_goal)
            self.daily_goal = max(1, int(daily_goal))
        if snooze_min is not None:
            self._meta["snooze_min"] = max(1, int(snooze_min))

    # ---- persistent reminder de-dup (survives worker restarts) ---------
    def reminder_sent(self, key: str) -> bool:
        sent = self._meta.get("sent_slots")
        return isinstance(sent, list) and key in sent

    def mark_reminder_sent(self, key: str) -> None:
        day = key.split("|", 1)[0]
        sent = self._meta.get("sent_slots")
        sent = list(sent) if isinstance(sent, list) else []
        # Keep only today's keys so it never grows without bound.
        sent = [k for k in sent if k.split("|", 1)[0] == day]
        if key not in sent:
            sent.append(key)
        self._meta["sent_slots"] = sent

    def prune(self, today: date, keep_days: int = 120) -> None:
        cutoff = (today - timedelta(days=keep_days)).isoformat()
        self._days = {k: v for k, v in self._days.items() if k >= cutoff}

    def save(self) -> None:
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = f"{self.path}.tmp"
        payload = {"meta": self._meta, "days": self._days}
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        os.replace(tmp, self.path)
