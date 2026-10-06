from datetime import datetime, timedelta, timezone

import requests

from ainews.clock import JOBS, Scheduler, job_for, last_slot, should_run

UTC = timezone.utc


def at(h, m=0, day=6):
    return datetime(2026, 10, day, h, m, tzinfo=UTC)


class FakeActions:
    def __init__(self, existing=None, fail=False):
        self.existing = existing or {}     # workflow -> [created_at, ...]
        self.dispatched = []
        self.fail = fail

    def runs_since(self, workflow, since, exclude_run_id=None):
        if self.fail:
            raise requests.ConnectionError("api down")
        return sum(1 for t in self.existing.get(workflow, []) if t >= since)

    def dispatch(self, workflow):
        self.dispatched.append(workflow)


class Now:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def test_slots():
    channel, bot = job_for("digest-channel.yml"), job_for("digest-bot.yml")
    assert last_slot(channel, at(13, 42)) == at(13)
    assert last_slot(bot, at(0, 0)) == at(0)          # 08:00 SGT
    assert last_slot(bot, at(9, 59)) == at(0)
    assert last_slot(bot, at(10, 1)) == at(10)        # 18:00 SGT
    assert last_slot(bot, at(23, 0)) == at(10)
    assert last_slot(bot, at(0, 30, day=7)) == at(0, day=7)


def test_starts_each_job_once_per_slot():
    actions, now = FakeActions(), Now(at(10, 0))
    sched = Scheduler(actions, now=now)
    sched.tick()
    sched.tick()                                      # same slot: nothing new
    assert sorted(actions.dispatched) == ["digest-bot.yml", "digest-channel.yml"]

    now.t = at(10, 50)
    sched.tick()
    assert len(actions.dispatched) == 2
    now.t = at(11, 0)                                 # next hour: channel only
    sched.tick()
    assert actions.dispatched[-1] == "digest-channel.yml"
    assert actions.dispatched.count("digest-bot.yml") == 1


def test_skips_slot_that_already_ran():
    # e.g. GitHub's schedule (or a manual run) already started it this slot.
    actions = FakeActions({"digest-channel.yml": [at(10, 0) + timedelta(seconds=20)],
                           "digest-bot.yml": [at(10, 0)]})
    Scheduler(actions, now=Now(at(10, 1))).tick()
    assert actions.dispatched == []


def test_catch_up_after_restart_but_not_too_late():
    # Listener restarts at 13:16 UTC: the 18:00 SGT bot slot (10:00 UTC) was
    # missed and is still within its 6h catch-up; the channel's 13:00 slot is
    # caught up too.
    actions = FakeActions()
    Scheduler(actions, now=Now(at(13, 16))).tick()
    assert sorted(actions.dispatched) == ["digest-bot.yml", "digest-channel.yml"]

    # Restart at 16:30 UTC: bot slot is 6.5h old — too late, wait for 08:00.
    actions = FakeActions()
    Scheduler(actions, now=Now(at(16, 30))).tick()
    assert actions.dispatched == ["digest-channel.yml"]


def test_api_errors_retry_on_next_tick():
    actions, now = FakeActions(fail=True), Now(at(10, 0))
    sched = Scheduler(actions, now=now)
    sched.tick()
    assert actions.dispatched == []
    actions.fail = False
    now.t = at(10, 1)
    sched.tick()
    assert sorted(actions.dispatched) == ["digest-bot.yml", "digest-channel.yml"]


def test_should_run_for_late_schedule_runs():
    # Listener started the 18:00 SGT digest; GitHub's schedule fires at 03:00
    # SGT (19:00 UTC) — it must skip.
    actions = FakeActions({"digest-bot.yml": [at(10, 0)]})
    assert should_run(actions, "digest-bot.yml", at(19, 0), "123") is False
    # Nothing ran this slot (listener was down): the backup goes ahead.
    assert should_run(FakeActions(), "digest-bot.yml", at(19, 0), "123") is True
    # Can't check: don't block the digest.
    assert should_run(FakeActions(fail=True), "digest-bot.yml",
                      at(19, 0), "123") is True


def test_listener_ticks_the_scheduler(tmp_path):
    from ainews.config import Config
    from ainews.listener import serve
    from ainews.subscribers import SubscriberStore

    class Clock:
        t = 0.0

        def __call__(self):
            return self.t

    clock = Clock()

    class Client:
        def get_updates(self, offset=0, limit=100, poll_timeout=0):
            clock.t += 30
            return []

    ticks = []

    class Sched:
        def tick(self):
            ticks.append(clock.t)
            if len(ticks) == 2:
                raise RuntimeError("boom")    # must not stop the listener

    cfg = Config(subscriber_file=str(tmp_path / "s.json"))
    serve(Client(), SubscriberStore(cfg.subscriber_file), cfg, minutes=2,
          clock=clock, sleep=lambda s: None, scheduler=Sched())
    assert len(ticks) == 4


def test_jobs_cover_both_workflows():
    assert {j.workflow for j in JOBS} == {"digest-channel.yml", "digest-bot.yml"}
