from datetime import datetime, timedelta, timezone

from ainews.classifier import classify
from ainews.formatter import MAX_CAPTION_LEN, render_post
from ainews.models import Article
from ainews.ranker import rank, score_article


def _art(title, **kw):
    a = Article(title=title, link=kw.pop("link", "https://example.com/a"),
                source=kw.pop("source", "Src"), **kw)
    return classify(a)


def test_post_includes_title_meta_and_takeaways():
    a = _art("Anthropic ships Claude Opus 4.8", source="Anthropic News",
             region="official")
    a.takeaways = ["Faster reasoning", "Cheaper tokens", "Better at code"]
    post = render_post(a)
    assert "Claude Opus 4.8" in post
    assert "Anthropic News" in post
    assert "🟧 Claude" in post           # platform badge
    assert "📣 Official" in post          # region badge
    assert "🤖 AI Platform" in post       # category tag
    for t in a.takeaways:
        assert t in post
    assert "Read more" in post


def test_post_falls_back_to_blurb_without_takeaways():
    a = _art("Some AI news", summary="A short blurb about the news.")
    post = render_post(a)
    assert "A short blurb about the news." in post


def test_post_escapes_html():
    a = _art("Tom & Jerry <x> AI")
    a.takeaways = ["A & B < C"]
    post = render_post(a)
    assert "&amp;" in post and "&lt;x&gt;" in post
    assert "<x>" not in post


def test_post_respects_caption_limit():
    a = _art("Headline " * 30)
    a.takeaways = ["word " * 100, "more " * 100, "lots " * 100]
    post = render_post(a, max_len=MAX_CAPTION_LEN)
    assert len(post) <= MAX_CAPTION_LEN


def test_ranking_puts_industry_last():
    # Platforms (priority #1) and agentic commerce both outrank generic
    # industry news; industry should land at the bottom.
    now = datetime.now(timezone.utc)
    industry = _art("Generic AI funding round", published=now)
    platform = _art("Claude gets an update", published=now)
    agentic = _art("Visa launches agentic commerce", source="PYMNTS",
                   published=now)
    ranked = rank([industry, platform, agentic], limit=3)
    assert ranked[-1] is industry
    assert industry not in ranked[:2]
    assert platform in ranked[:2] and agentic in ranked[:2]


def test_ranking_caps_to_limit():
    now = datetime.now(timezone.utc)
    arts = [_art(f"AI item {i}", link=f"https://x/{i}", published=now)
            for i in range(20)]
    assert len(rank(arts, limit=10)) == 10


def test_platform_priority_order_in_score():
    now = datetime.now(timezone.utc)
    claude = _art("Claude news", published=now)
    grok = _art("Grok news", published=now)
    # Claude is higher priority than Grok, so should score higher.
    assert score_article(claude) > score_article(grok)
