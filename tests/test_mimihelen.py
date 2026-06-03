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


# ---- Q&A ---------------------------------------------------------------
from types import SimpleNamespace
from mimihelen import qa


class _Tracker:
    def __init__(self, n=0, streak=0):
        self._n = n
        self._streak = streak
    def doses_on(self, d):
        return self._n
    def streak(self, d):
        return self._streak


def _cfg(**kw):
    base = dict(times=["07:00", "12:00", "18:00", "22:00"], tz="Asia/Singapore",
                daily_goal=4, eyedrops="", anthropic_api_key="", qa_model="x")
    base.update(kw)
    return SimpleNamespace(**base)


def test_next_reminder_same_day_and_wrap():
    times = ["07:00", "12:00", "18:00", "22:00"]
    s = qa.next_reminder(times, datetime(2026, 6, 3, 9, 0))
    assert "12:00" in s and "today" in s and "in 3h" in s
    # after the last slot -> tomorrow's first
    s2 = qa.next_reminder(times, datetime(2026, 6, 3, 23, 0))
    assert "07:00" in s2 and "tomorrow" in s2


def test_answer_next_reminder_intent():
    a = qa.answer("what time is my next reminder?", _cfg(), _Tracker(), datetime(2026, 6, 3, 9, 0))
    assert "12:00" in a and "next drops" in a.lower()


def test_answer_schedule_and_progress_and_streak():
    now = datetime(2026, 6, 3, 9, 0)
    assert "07:00" in qa.answer("show me my schedule", _cfg(), _Tracker(), now)
    assert "2/4" in qa.answer("how many drops today", _cfg(), _Tracker(n=2), now)
    assert "3 day" in qa.answer("what's my streak", _cfg(), _Tracker(streak=3), now)


def test_answer_eyedrop_info_uses_configured_rx():
    now = datetime(2026, 6, 3, 9, 0)
    generic = qa.answer("what eyedrops am i using?", _cfg(), _Tracker(), now)
    assert "artificial tears" in generic.lower()  # general primer
    specific = qa.answer("what are my drops for?",
                         _cfg(eyedrops="lubricating drops for dry eyes"), _Tracker(), now)
    assert "lubricating drops for dry eyes" in specific


def test_answer_no_rub_and_howto():
    now = datetime(2026, 6, 3, 9, 0)
    assert "rub" in qa.answer("can i rub my eyes?", _cfg(), _Tracker(), now).lower()
    howto = qa.answer("how do i use the eyedrops?", _cfg(), _Tracker(), now)
    assert "wash your hands" in howto.lower()


def test_answer_unknown_without_llm_lists_options():
    now = datetime(2026, 6, 3, 9, 0)
    a = qa.answer("tell me a joke about cats", _cfg(), _Tracker(), now)
    assert "next reminder" in a.lower()  # falls back to the helpful menu


# ---- tips: more of them, no same-day repeats ---------------------------
def test_plenty_of_tips():
    assert content.tip_count() >= 20


def test_tips_no_repeat_within_a_day():
    # The day's reminders (and on-demand /tip) must never repeat a tip until
    # the whole list is exhausted.
    n = min(content.tip_count(), 8)
    tips = [content.tip_for_slot("2026-06-03", i) for i in range(n)]
    assert len(set(tips)) == n


def test_tip_order_varies_by_day():
    a = [content.tip_for_slot("2026-06-03", i) for i in range(4)]
    b = [content.tip_for_slot("2026-06-09", i) for i in range(4)]
    assert a != b


def test_build_reminder_uses_distinct_tips_across_day_slots():
    msgs = [content.build_reminder("Helen", f"2026-06-03|{t}",
                                   dose_label=f"dose {i+1} of 4", tip_index=i)
            for i, t in enumerate(["07:00", "12:00", "18:00", "22:00"])]
    # Extract the tip line (4th-from-last block) — simplest: ensure the set of
    # full messages differ and no two share the same tip by checking the tips.
    tips = [content.tip_for_slot("2026-06-03", i) for i in range(4)]
    for m, tip in zip(msgs, tips):
        assert tip in m
    assert len(set(tips)) == 4


# ---- undo (accidental Done) -------------------------------------------
def test_undo_dose_removes_last(tmp_path):
    t = DoseTracker(str(tmp_path / "u.json"), daily_goal=4)
    d = datetime(2026, 6, 3, 9, 0)
    t.log_dose(d)
    t.log_dose(d.replace(hour=12))
    assert t.doses_on(d.date()) == 2
    assert t.undo_dose(d.date()) == 1        # removes the 12:00 one
    assert t.times_on(d.date()) == ["09:00"]
    assert t.undo_dose(d.date()) == 0        # removes the 09:00 one
    assert t.undo_dose(d.date()) is None     # nothing left to undo
    assert t.doses_on(d.date()) == 0


def test_undo_persists(tmp_path):
    path = str(tmp_path / "u.json")
    t = DoseTracker(path, daily_goal=4)
    d = datetime(2026, 6, 3, 9, 0)
    t.log_dose(d); t.log_dose(d.replace(hour=12))
    t.undo_dose(d.date()); t.save()
    again = DoseTracker(path, daily_goal=4)
    assert again.doses_on(date(2026, 6, 3)) == 1


# ---- 200+ tips: unique, HTML-safe, no same-day repeats over weeks --------
def test_two_hundred_tips_unique_and_safe():
    import re
    tips = content.EYE_CARE_TIPS
    assert content.tip_count() >= 200
    assert len(set(tips)) == len(tips)                 # all distinct
    for t in tips:
        assert "<" not in t and ">" not in t           # Telegram HTML-safe
        assert not re.search(r'&(?!amp;|lt;|gt;|quot;|#\d+;)', t)


def test_no_same_day_repeats_for_weeks():
    # 4 reminders/day for 3 weeks should never repeat a tip within any day.
    from datetime import date, timedelta
    start = date(2026, 6, 1)
    for d in range(21):
        day = (start + timedelta(days=d)).isoformat()
        tips = [content.tip_for_slot(day, i) for i in range(4)]
        assert len(set(tips)) == 4


# ---- change schedule + persistence ------------------------------------
from mimihelen.config import parse_time_list
from mimihelen.bot import MimiHelenBot


def test_parse_time_list():
    assert parse_time_list("8:00, 13:30; 19:00 22:5") == ["08:00", "13:30", "19:00", "22:05"]
    assert parse_time_list("07:00, 07:00, 25:00, oops, 12:61") == ["07:00"]  # dedupe + drop invalid
    assert parse_time_list("") == []
    assert parse_time_list("22:00, 06:00") == ["06:00", "22:00"]            # sorted


def test_tracker_schedule_override_persists(tmp_path):
    p = str(tmp_path / "s.json")
    t = DoseTracker(p, daily_goal=4)
    t.set_schedule(times=["08:00", "20:00"], daily_goal=2)
    t.save()
    again = DoseTracker(p, daily_goal=4)
    assert again.get_times() == ["08:00", "20:00"]
    assert again.get_daily_goal() == 2


def test_config_apply_state_overrides(tmp_path):
    t = DoseTracker(str(tmp_path / "s.json"), daily_goal=4)
    t.set_schedule(times=["09:00", "21:00"], daily_goal=2)
    cfg = Config.from_env()
    cfg.apply_state_overrides(t)
    assert cfg.times == ["09:00", "21:00"] and cfg.daily_goal == 2


def test_persistent_reminder_dedup(tmp_path):
    p = str(tmp_path / "s.json")
    t = DoseTracker(p, daily_goal=4)
    assert not t.reminder_sent("2026-06-03|07:00")
    t.mark_reminder_sent("2026-06-03|07:00")
    t.save()
    again = DoseTracker(p, daily_goal=4)
    assert again.reminder_sent("2026-06-03|07:00")          # survives restart
    again.mark_reminder_sent("2026-06-04|07:00")            # new day prunes old
    assert not again.reminder_sent("2026-06-03|07:00")


def _bot(tmp_path, **cfgkw):
    cfg = Config.from_env()
    cfg.chat_id = "1"; cfg.tz = "Asia/Singapore"
    for k, v in cfgkw.items():
        setattr(cfg, k, v)
    class Mock:
        def __init__(self): self.sent = []
        def send_message(self, text, chat_id=None, reply_markup=None, **k):
            self.sent.append(text)
        def answer_callback_query(self, *a, **k): pass
    return MimiHelenBot(cfg, Mock(), DoseTracker(str(tmp_path / "s.json"), daily_goal=cfg.daily_goal)), cfg


def test_change_schedule_command(tmp_path):
    bot, cfg = _bot(tmp_path, times=["07:00", "12:00", "18:00", "22:00"], daily_goal=4)
    out = bot._change_schedule("08:00, 13:00, 20:00")
    assert "08:00, 13:00, 20:00" in out
    assert cfg.times == ["08:00", "13:00", "20:00"]   # in-memory takes effect now
    assert cfg.daily_goal == 3
    assert bot.tracker.get_times() == ["08:00", "13:00", "20:00"]  # persisted
    # garbage input -> help, schedule unchanged
    out2 = bot._change_schedule("haha no times")
    assert "/schedule" in out2 and cfg.times == ["08:00", "13:00", "20:00"]


def test_tick_uses_persistent_dedup(tmp_path):
    from datetime import datetime as _dt
    bot, cfg = _bot(tmp_path, times=["07:00", "12:00", "18:00", "22:00"], daily_goal=4,
                    slot_tolerance_min=30)
    now = _dt(2026, 6, 3, 12, 2)
    assert bot.tick(now) is True               # sends 12:00
    assert bot.tick(_dt(2026, 6, 3, 12, 6)) is False   # already sent (persisted)
    # a brand-new handler (simulating a worker restart) must not re-send
    bot2 = MimiHelenBot(cfg, bot.client, DoseTracker(str(tmp_path / "s.json"), daily_goal=4))
    assert bot2.tick(_dt(2026, 6, 3, 12, 8)) is False


# ---- snooze: configurable + non-blocking countdown ---------------------
from datetime import timedelta as _td
from mimihelen import telegram as _tg


def test_snooze_button_label_reflects_minutes():
    kb = _tg.reminder_keyboard(5)
    labels = [b["text"] for row in kb["inline_keyboard"] for b in row]
    assert "⏰ Snooze 5m" in labels
    kb2 = _tg.reminder_keyboard(15)
    assert any("Snooze 15m" in l for l in [b["text"] for row in kb2["inline_keyboard"] for b in row])


def test_snooze_min_config_and_override(tmp_path, monkeypatch):
    monkeypatch.setenv("MIMIHELEN_SNOOZE_MIN", "7")
    cfg = Config.from_env()
    assert cfg.snooze_min == 7
    t = DoseTracker(str(tmp_path / "s.json"), daily_goal=4)
    t.set_schedule(snooze_min=3)
    cfg.apply_state_overrides(t)         # chat-set override wins
    assert cfg.snooze_min == 3


class _RecClient:
    """Records messages/edits and hands out message ids."""
    def __init__(self):
        self.sent, self.edits, self._id = [], [], 0
    def send_message(self, text, chat_id=None, reply_markup=None, **k):
        self._id += 1
        self.sent.append((self._id, text))
        return {"ok": True, "result": {"message_id": self._id}}
    def edit_message_text(self, chat_id, message_id, text, **k):
        self.edits.append((message_id, text))
        return {"ok": True}
    def answer_callback_query(self, *a, **k): pass


def _snooze_bot(tmp_path):
    cfg = Config.from_env(); cfg.chat_id = "1"; cfg.tz = "Asia/Singapore"; cfg.snooze_min = 5
    return MimiHelenBot(cfg, _RecClient(), DoseTracker(str(tmp_path / "s.json"), daily_goal=4)), cfg


def test_snooze_is_nonblocking_with_countdown_then_fires(tmp_path):
    bot, cfg = _snooze_bot(tmp_path)
    t0 = datetime(2026, 6, 3, 9, 0, 0)
    bot._start_snooze("1", t0)   # what the snooze button triggers (now passed in)
    # returns immediately, one countdown message posted, nothing slept
    assert bot.has_pending() and len(bot.client.sent) == 1
    # 2 minutes in -> the countdown message is edited, not re-sent
    bot.process_pending(t0 + _td(minutes=2))
    assert bot.has_pending()
    assert any("left" in txt for _, txt in bot.client.edits)
    assert len(bot.client.sent) == 1                      # still just the countdown msg
    # at/after 5 min -> reminder is sent and the countdown clears
    bot.process_pending(t0 + _td(minutes=5, seconds=1))
    assert not bot.has_pending()
    assert any("snooze over" in txt for _, txt in bot.client.sent)


def test_set_snooze_command(tmp_path):
    bot, cfg = _snooze_bot(tmp_path)
    out = bot._set_snooze("10")
    assert "10 min" in out and cfg.snooze_min == 10
    assert bot.tracker.get_snooze_min() == 10
    assert "snooze is" in bot._set_snooze("").lower()      # bare shows current
    assert "number" in bot._set_snooze("abc").lower()      # invalid


def test_snooze_survives_restart(tmp_path):
    # Press snooze, then simulate a worker restart: a NEW handler must reload the
    # pending snooze from state and still fire the reminder.
    path = str(tmp_path / "s.json")
    cfg = Config.from_env(); cfg.chat_id = "1"; cfg.tz = "Asia/Singapore"; cfg.snooze_min = 5
    bot1 = MimiHelenBot(cfg, _RecClient(), DoseTracker(path, daily_goal=4))
    t0 = datetime(2026, 6, 3, 9, 0, 0)
    bot1._start_snooze("1", t0)
    assert bot1.tracker.get_pending_snoozes()                 # persisted

    # restart: brand-new handler + tracker from the same file
    bot2 = MimiHelenBot(cfg, _RecClient(), DoseTracker(path, daily_goal=4))
    bot2.load_pending()
    assert bot2.has_pending()                                 # restored
    bot2.process_pending(t0 + _td(minutes=5, seconds=1))      # fires after restart
    assert any("snooze over" in txt for _, txt in bot2.client.sent)
    assert not bot2.has_pending()
    assert bot2.tracker.get_pending_snoozes() == []           # cleared from state
