"""Tests for Mimi Helen Bot — content, scheduling and dose tracking.

All offline: no network, no real Telegram calls.
"""

from datetime import date, datetime, timedelta

import pytest

from mimihelen import content
from mimihelen.config import Config, _times
from mimihelen.schedule import Slot, current_slot, nearest_slot
from mimihelen.tracker import DoseTracker


# ---- content -----------------------------------------------------------
def test_reminder_has_drops_norub_and_tip():
    msg = content.build_reminder("Helen", "2026-06-03|08:00",
                                 dose_label="dose 1 of 4", include_howto=True)
    assert "Helen" in msg
    assert "eyedrops" in msg.lower()
    assert "rub" in msg.lower()            # the no-rub nudge is always present
    assert "dose 1 of 4" in msg
    assert "how-to" in msg.lower()         # first slot carries the steps


def test_reminder_is_deterministic_per_seed():
    a = content.build_reminder("Helen", "seedX")
    b = content.build_reminder("Helen", "seedX")
    c = content.build_reminder("Helen", "seedY")
    assert a == b           # same seed -> identical wording
    # Different seeds usually differ; at minimum the function is stable.
    assert isinstance(c, str) and c


def test_no_howto_when_not_first():
    msg = content.build_reminder("Helen", "s", include_howto=False)
    assert "how-to" not in msg.lower()


# ---- config parsing ----------------------------------------------------
def test_times_parsing_normalises_and_defaults(monkeypatch):
    assert _times("X", ["08:00"]) == ["08:00"]      # unset -> default
    monkeypatch.setenv("X", "8:00, 12:30 ; 20:5")
    assert _times("X", ["00:00"]) == ["08:00", "12:30", "20:05"]


def test_config_from_env_defaults():
    cfg = Config.from_env()
    assert cfg.daily_goal == 4
    assert len(cfg.times) >= 3          # covers the 3-5/day goal
    assert cfg.friend_name


# ---- scheduling --------------------------------------------------------
TIMES = ["08:00", "12:30", "16:00", "20:00", "22:30"]


def test_current_slot_matches_nearest_within_tolerance():
    now = datetime(2026, 6, 3, 12, 35)         # 5 min after 12:30
    slot = current_slot(TIMES, now, tolerance_min=30)
    assert slot is not None
    assert slot.time_str == "12:30"
    assert slot.index == 1 and slot.total == 5
    assert slot.dose_label == "dose 2 of 5"
    assert not slot.is_first


def test_current_slot_first_of_day():
    slot = current_slot(TIMES, datetime(2026, 6, 3, 8, 2), tolerance_min=30)
    assert slot is not None and slot.is_first and slot.index == 0


def test_current_slot_none_outside_tolerance():
    now = datetime(2026, 6, 3, 14, 0)          # far from any slot
    assert current_slot(TIMES, now, tolerance_min=30) is None


def test_nearest_slot_always_returns():
    now = datetime(2026, 6, 3, 14, 0)
    slot = nearest_slot(TIMES, now)
    assert isinstance(slot, Slot)
    # 14:00 is closer to 12:30 (90m) than 16:00 (120m).
    assert slot.time_str == "12:30"


# ---- tracker -----------------------------------------------------------
def test_log_dose_and_progress(tmp_path):
    t = DoseTracker(str(tmp_path / "s.json"), daily_goal=4)
    d = datetime(2026, 6, 3, 9, 0)
    assert t.doses_on(d.date()) == 0
    assert t.log_dose(d) == 1
    assert t.log_dose(d.replace(hour=12)) == 2
    assert t.doses_on(d.date()) == 2
    assert not t.goal_met(d.date())
    assert t.times_on(d.date()) == ["09:00", "12:00"]


def test_tracker_persists_across_instances(tmp_path):
    path = str(tmp_path / "s.json")
    t = DoseTracker(path, daily_goal=2)
    t.log_dose(datetime(2026, 6, 3, 9, 0))
    t.save()
    again = DoseTracker(path, daily_goal=2)
    assert again.doses_on(date(2026, 6, 3)) == 1


def test_streak_counts_consecutive_goal_days(tmp_path):
    t = DoseTracker(str(tmp_path / "s.json"), daily_goal=2)
    today = date(2026, 6, 3)
    # Meet the goal today and the two days before.
    for offset in (0, 1, 2):
        day = today - timedelta(days=offset)
        for hour in (9, 18):
            t.log_dose(datetime(day.year, day.month, day.day, hour))
    assert t.streak(today) == 3


def test_streak_allows_unfinished_today(tmp_path):
    t = DoseTracker(str(tmp_path / "s.json"), daily_goal=2)
    today = date(2026, 6, 3)
    yesterday = today - timedelta(days=1)
    for hour in (9, 18):                       # yesterday met goal
        t.log_dose(datetime(yesterday.year, yesterday.month, yesterday.day, hour))
    t.log_dose(datetime(today.year, today.month, today.day, 9))  # today: 1/2
    # Unfinished today shouldn't zero out a real streak.
    assert t.streak(today) == 1


def test_corrupt_state_does_not_crash(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{ this is not json", encoding="utf-8")
    t = DoseTracker(str(path), daily_goal=2)
    assert t.doses_on(date(2026, 6, 3)) == 0    # degrades gracefully


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
