"""Coverage gaps found on 6-7 Oct 2026: the Amex agentic playbook and
Sierra's Personal Agent Protocol were missed while filler went out."""

from datetime import datetime, timedelta, timezone

import feedparser
import pytest

from ainews import digest, fetcher
from ainews.classifier import classify, is_ai_relevant, is_low_value
from ainews.config import Config
from ainews.models import CAT_AGENTIC, Article
from ainews.ranker import score_article
from ainews.sources import WATCH_FEEDS, Feed
from ainews.state import SeenStore

NOW = datetime.now(timezone.utc)


def _a(title, summary="", region="global", source="Src"):
    return classify(Article(title=title, link="https://x/" + title[:20],
                            source=source, region=region, summary=summary,
                            uid=title, published=NOW - timedelta(hours=1)))


@pytest.mark.parametrize("title", [
    "Sierra and Meta introduce Personal Agent Protocol",
    "Meta and Sierra announce open standard for AI agent interactions",
    "Meta is helping develop an AI agent protocol that defines how personal "
    "agents interact with businesses",
    "American Express launches Business Playbook for Agentic Commerce",
    "Visa expands Trusted Agent Protocol to Asia",
    "AI agents can now shop at Walmart with saved cards",
])
def test_missed_stories_now_rank_as_agentic(title):
    a = _a(title)
    assert a.category == CAT_AGENTIC
    assert score_article(a) >= 16          # competes with platform news


@pytest.mark.parametrize("title", [
    "Insurers brace for millions in claims as AI agents spin out of control",
    "AlphaSense unveils SuperAnalyst AI agent",
    "Travel agent bookings rebound in Asia",
])
def test_agent_stories_without_commerce_stay_general(title):
    assert _a(title).category != CAT_AGENTIC


@pytest.mark.parametrize("title", [
    "Vipps MobilePay becomes Vipps across the Nordics",
    "Gatehouse Bank backs youth homeless charity via new saver account",
    "Call Federal Credit Union goes live with Mahalo platform",
    "Scrimshaw Jukebox",
])
def test_off_topic_filler_is_not_ai(title):
    assert not is_ai_relevant(_a(title))


@pytest.mark.parametrize("title", [
    "Plaid launches credit, fraud and payment risk AI models",
    "Mistral Large 4 is Europe's trillion-parameter answer to US models",
    "DeepSeek Looks to Raise $12 Billion Ahead of IPO",
    "Insurers brace for millions in claims as AI agents spin out of control",
])
def test_real_ai_news_passes(title):
    a = _a(title, summary="An artificial intelligence story.")
    assert is_ai_relevant(a) and not is_low_value(a)


@pytest.mark.parametrize("title", [
    "datasette-atom 0.11a0", "llm-mistral 0.16", "llm-openai-decisions 0.1a0",
    "Quoting Victoria Kim",
])
def test_release_notes_and_quotes_are_low_value(title):
    assert is_low_value(_a(title))


def test_quiet_hour_sends_fewer_not_filler(tmp_path, monkeypatch):
    feed = [_a("Vipps MobilePay becomes Vipps across the Nordics"),
            _a("datasette-atom 0.11a0", summary="An AI tool release."),
            _a("Sierra and Meta introduce Personal Agent Protocol"),
            _a("Real-time payments in Asia Pacific", region="expert",
               source="Agenda: Payments (Jeremy Light)")]
    monkeypatch.setattr(digest, "fetch_all", lambda *a, **k: list(feed))
    picked = digest.select_articles(Config(max_items=5),
                                    SeenStore(str(tmp_path / "s.json")), 24)
    # Expert newsletters are exempt; filler and release notes are dropped.
    assert sorted(a.title for a in picked) == [
        "Real-time payments in Asia Pacific",
        "Sierra and Meta introduce Personal Agent Protocol"]
    # The switch turns the bar off.
    picked = digest.select_articles(Config(max_items=5, ai_only=False),
                                    SeenStore(str(tmp_path / "t.json")), 24)
    assert len(picked) == 4


GNEWS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Meta joins companies to tame 'chaos' of doing business with AI bots - CNBC</title>
<link>https://news.google.com/rss/articles/abc</link><guid>abc</guid>
<pubDate>Tue, 06 Oct 2026 18:15:16 GMT</pubDate>
<description>&lt;a href="x"&gt;Meta joins companies&lt;/a&gt;&amp;nbsp;CNBC</description>
<source url="https://www.cnbc.com">CNBC</source></item>
<item><title>Amex launches agentic playbook - Stock Titan - Stock Titan</title>
<link>https://news.google.com/rss/articles/def</link><guid>def</guid>
<pubDate>Tue, 06 Oct 2026 12:30:00 GMT</pubDate>
<source url="https://www.stocktitan.net">Stock Titan</source></item>
</channel></rss>"""


def _gnews_feed(any_source=False):
    return Feed("Google News: x", "https://news.google.com/rss/search?q=x",
                "global", "gnews", any_source=any_source)


def test_google_news_entries_credit_the_real_outlet():
    parsed = feedparser.parse(GNEWS)
    art = fetcher._entry_to_article(parsed.entries[0], _gnews_feed())
    assert art.title == ("Meta joins companies to tame 'chaos' of doing "
                         "business with AI bots")
    assert art.source == "CNBC"
    assert art.summary == ""                 # link-list blurb dropped


def test_google_news_drops_untrusted_sites_unless_feed_allows_any():
    parsed = feedparser.parse(GNEWS)
    stock_titan = parsed.entries[1]          # not a recognised outlet
    assert fetcher._entry_to_article(stock_titan, _gnews_feed()) is None
    art = fetcher._entry_to_article(stock_titan, _gnews_feed(any_source=True))
    assert art.title == "Amex launches agentic playbook - Stock Titan"
    assert art.source == "Stock Titan"


@pytest.mark.parametrize("url,ok", [
    ("https://www.cnbc.com", True), ("https://finance.yahoo.com", True),
    ("https://www.businesswire.com", True), ("https://www.stocktitan.net", False),
    ("https://notcnbc.com", False), ("", False)])
def test_trusted_domains(url, ok):
    from ainews.sources import is_trusted_domain
    assert is_trusted_domain(url) is ok


@pytest.mark.parametrize("title", [
    "REVERSIBLE Launches Agentic Affiliate Platform Connecting AI Shopping "
    "to 700+ Premium Retailers",
    "allow agents to buy from any online store using a single API",
])
def test_agent_commerce_startup_launches_rank_as_agentic(title):
    assert _a(title).category == CAT_AGENTIC


def test_duplicate_check_sends_blurbs(monkeypatch):
    """The CNBC 'tame chaos' headline only matches the protocol story via
    its blurb, so the semantic check must see blurbs."""
    import json
    import sys
    import types
    from ainews import cluster
    sent = {}

    class Msgs:
        def create(self, **kw):
            sent.update(json.loads(kw["messages"][0]["content"].split("\n\n", 1)[1]))
            raise RuntimeError("stop after capturing the request")

    fake = types.SimpleNamespace(Anthropic=lambda **k: types.SimpleNamespace(messages=Msgs()))
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    arts = [_a("Meta joins companies to tame chaos of doing business with AI bots",
               summary="Meta, Walmart and Sierra publish a personal agent protocol.")]
    cluster.cluster_duplicates(arts, ["Introducing Personal Agent Protocol"],
                               api_key="k", model="m")
    assert "personal agent protocol" in sent["candidates"][0]["blurb"]


def test_sitemap_path_prefix_skips_translations():
    xml = b"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://sierra.ai/blog/introducing-personal-agent-protocol</loc></url>
      <url><loc>https://sierra.ai/es/blog/introducing-personal-agent-protocol</loc></url>
      <url><loc>https://sierra.ai/customers/sonos</loc></url></urlset>"""
    posts, _ = fetcher._parse_sitemap(xml, "/blog/")
    assert [u for u, _ in posts] == [
        "https://sierra.ai/blog/introducing-personal-agent-protocol"]


def test_watch_feeds_cover_both_missed_sources():
    names = " ".join(f.name for f in WATCH_FEEDS)
    assert "Sierra" in names and "agentic commerce" in names
    assert all("when%3A1d" in f.url for f in WATCH_FEEDS if f.kind == "gnews")
