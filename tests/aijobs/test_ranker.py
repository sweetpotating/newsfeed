from datetime import datetime, timedelta, timezone

from aijobs.models import Job
from aijobs.ranker import rank, score_job


def _job(**kw):
    base = dict(title="x", company="c", location="Singapore", url="u", uid="i")
    base.update(kw)
    return Job(**base)


def test_priority_lab_outranks_non_lab():
    lab = _job(uid="a", is_priority_lab=True, role_tags=["data"])
    other = _job(uid="b", is_priority_lab=False, role_tags=["research"])
    assert score_job(lab) > score_job(other)


def test_research_outranks_data_within_same_company():
    research = _job(uid="a", role_tags=["research"])
    data = _job(uid="b", role_tags=["data"])
    assert score_job(research) > score_job(data)


def test_recency_breaks_ties():
    now = datetime.now(timezone.utc)
    fresh = _job(uid="a", role_tags=["ml"], posted=now)
    old = _job(uid="b", role_tags=["ml"], posted=now - timedelta(days=30))
    assert score_job(fresh) > score_job(old)


def test_rank_caps_and_orders():
    jobs = [
        _job(uid="lab", is_priority_lab=True, role_tags=["research"]),
        _job(uid="mid", role_tags=["ml"]),
        _job(uid="low", role_tags=["data"]),
    ]
    ranked = rank(jobs, limit=2)
    assert len(ranked) == 2
    assert ranked[0].uid == "lab"
