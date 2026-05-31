from datetime import datetime, timedelta, timezone

from aijobs.formatter import render_header, render_post
from aijobs.models import Job


def _job(**kw):
    base = dict(title="Research Scientist", company="Anthropic",
                location="Singapore", url="https://x/y", uid="u1")
    base.update(kw)
    return Job(**base)


def test_render_post_basics():
    j = _job(is_priority_lab=True, role_tags=["research"],
             posted=datetime.now(timezone.utc) - timedelta(hours=2))
    out = render_post(j)
    assert "⭐" in out
    assert "Research Scientist" in out
    assert "Anthropic" in out
    assert "Singapore" in out
    assert "🔬 Research" in out
    assert 'href="https://x/y"' in out
    assert "Apply →" in out
    assert "2h ago" in out


def test_non_priority_has_no_star():
    out = render_post(_job(company="Grab", is_priority_lab=False))
    assert "⭐" not in out


def test_html_escaping():
    j = _job(title="C++ & ML <Lead>", company="A&B")
    out = render_post(j)
    assert "&amp;" in out
    assert "&lt;Lead&gt;" in out
    assert "<Lead>" not in out  # raw angle brackets must be escaped


def test_summary_included_when_present():
    out = render_post(_job(summary="Own pretraining research."))
    assert "Own pretraining research." in out


def test_caption_truncation():
    out = render_post(_job(summary="x" * 5000), max_len=200)
    assert len(out) <= 200
    assert out.endswith("…")


def test_header_pluralisation():
    assert "1 new opening" in render_header(1)
    assert "3 new openings" in render_header(3)
