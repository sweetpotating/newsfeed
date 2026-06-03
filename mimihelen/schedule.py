"""Work out which reminder slot is due "right now".

The bot is told a list of clock times (e.g. 08:00, 12:30, 16:00, ...). In
``remind`` mode it runs from cron near one of those times; this module maps the
current wall-clock time to the nearest scheduled slot (within a tolerance) so
the reminder can be tagged "dose 2 of 4" and so the first slot of the day can
carry the full how-to.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

try:  # Python 3.9+ stdlib; fall back to UTC if the tz database is unavailable.
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def now_in_tz(tz: str) -> datetime:
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(tz))
        except Exception:  # unknown zone -> UTC, never crash a reminder
            pass
    return datetime.now(timezone.utc)


def _minutes(hhmm: str) -> int:
    hh, mm = hhmm.split(":")
    return int(hh) * 60 + int(mm)


@dataclass
class Slot:
    index: int           # 0-based position in the day's schedule
    total: int           # how many slots per day
    time_str: str        # "08:00"
    is_first: bool       # first slot of the day?

    @property
    def dose_label(self) -> str:
        return f"dose {self.index + 1} of {self.total}"


def current_slot(times: List[str], now: datetime,
                 tolerance_min: int = 30) -> Optional[Slot]:
    """Return the slot closest to ``now`` if within ``tolerance_min``, else None.

    Cron rarely fires to the exact second, so we match the nearest scheduled
    time and accept it when it's within the tolerance window.
    """
    if not times:
        return None
    ordered = sorted(times, key=_minutes)
    now_min = now.hour * 60 + now.minute

    best_idx, best_diff = 0, None
    for idx, t in enumerate(ordered):
        diff = abs(_minutes(t) - now_min)
        if best_diff is None or diff < best_diff:
            best_idx, best_diff = idx, diff

    if best_diff is None or best_diff > tolerance_min:
        return None
    return Slot(
        index=best_idx,
        total=len(ordered),
        time_str=ordered[best_idx],
        is_first=(best_idx == 0),
    )


def nearest_slot(times: List[str], now: datetime) -> Optional[Slot]:
    """Like ``current_slot`` but ignores tolerance — always returns a slot.

    Used for ``--force`` previews so a manual run can still be tagged sensibly.
    """
    return current_slot(times, now, tolerance_min=24 * 60)


def due_slot(times: List[str], now: datetime,
             catch_up_min: int = 30) -> Optional[Slot]:
    """The slot that is *due now* for the always-on serve worker.

    Unlike ``current_slot`` (symmetric tolerance, used by the cron), this only
    matches a slot whose time is **at or before** ``now`` and no more than
    ``catch_up_min`` minutes ago. So the worker fires reminders AT the scheduled
    time (never early), and still catches up a reminder it missed while it was
    restarting — without ever sending one ahead of time.
    """
    if not times:
        return None
    ordered = sorted(times, key=_minutes)
    now_min = now.hour * 60 + now.minute
    best = None
    for idx, t in enumerate(ordered):
        tmin = _minutes(t)
        if tmin <= now_min and (now_min - tmin) <= catch_up_min:
            best = idx  # keep the latest due slot
    if best is None:
        return None
    return Slot(index=best, total=len(ordered),
               time_str=ordered[best], is_first=(best == 0))

