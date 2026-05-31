"""End-to-end pipeline test with a stubbed fetcher (no network)."""

from datetime import datetime, timezone

from aijobs import digest
from aijobs.config import Config
from aijobs.models import Job
from aijobs.state import SeenStore
from aijobs.summarizer import summarize


def _job(uid, title, location, company="Anthropic", **kw):
    return Job(uid=uid, title=title, location=location, company=company,
               url=f"https://x/{uid}", **kw)


def _stub_fetch(jobs):
    return lambda companies, timeout: list(jobs)


def test_select_keeps_only_singapore_ai_roles(monkeypatch, tmp_path):
    catalogue = [
        _job("1", "Research Scientist", "Singapore"),            # keep
        _job("2", "Research Scientist", "London"),               # wrong loc
        _job("3", "Account Executive", "Singapore"),             # not AI
        _job("4", "ML Engineer", "Remote - Singapore",
             company="Grab"),                                    # keep
        _job("5", "Data Center Technician", "Singapore"),        # excluded
    ]
    monkeypatch.setattr(digest, "fetch_all", _stub_fetch(catalogue))
    cfg = Config(state_file=str(tmp_path / "s.json"))
    store = SeenStore(cfg.state_file)
    selected = digest.select_jobs(cfg, store, lookback_hours=10_000)
    uids = {j.uid for j in selected}
    assert uids == {"1", "4"}
    assert all(j.role_tags for j in selected)


def test_dedup_collapses_repeated_uid(monkeypatch, tmp_path):
    catalogue = [
        _job("dup", "ML Engineer", "Singapore"),
        _job("dup", "ML Engineer", "Singapore"),
    ]
    monkeypatch.setattr(digest, "fetch_all", _stub_fetch(catalogue))
    cfg = Config(state_file=str(tmp_path / "s.json"))
    store = SeenStore(cfg.state_file)
    selected = digest.select_jobs(cfg, store, lookback_hours=10_000)
    assert len(selected) == 1


def test_seen_jobs_are_skipped(monkeypatch, tmp_path):
    catalogue = [_job("seen", "ML Engineer", "Singapore")]
    monkeypatch.setattr(digest, "fetch_all", _stub_fetch(catalogue))
    cfg = Config(state_file=str(tmp_path / "s.json"))
    store = SeenStore(cfg.state_file)
    store.mark(["seen"])
    selected = digest.select_jobs(cfg, store, lookback_hours=10_000)
    assert selected == []


def test_lookback_drops_old_dated_jobs(monkeypatch, tmp_path):
    old = _job("old", "ML Engineer", "Singapore",
               posted=datetime(2000, 1, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(digest, "fetch_all", _stub_fetch([old]))
    cfg = Config(state_file=str(tmp_path / "s.json"))
    store = SeenStore(cfg.state_file)
    assert digest.select_jobs(cfg, store, lookback_hours=24) == []


def test_summarize_no_key_is_noop():
    jobs = [_job("1", "ML Engineer", "Singapore", summary="orig")]
    summarize(jobs, api_key="", model="claude-haiku-4-5")
    assert jobs[0].summary == "orig"  # unchanged, no crash
