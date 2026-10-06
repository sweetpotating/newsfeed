from datetime import datetime, timedelta, timezone

from ainews import digest, fetcher
from ainews.classifier import classify
from ainews.config import Config
from ainews.formatter import render_post
from ainews.models import CAT_AGENTIC, Article
from ainews.ranker import score_article
from ainews.sources import EXPERT_FEEDS, Feed, all_feeds
from ainews.state import SeenStore

NOW = datetime.now(timezone.utc)

SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/</loc></url>
  <url><loc>https://example.com/p/older-post</loc>
       <lastmod>2026-09-01T08:00:00Z</lastmod></url>
  <url><loc>https://example.com/p/agentic-bank-run</loc>
       <lastmod>2026-10-02T08:00:00Z</lastmod></url>
  <url><loc>https://example.com/authors/nik</loc></url>
</urlset>"""

SITEMAP_INDEX = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-posts.xml</loc></sitemap>
</sitemapindex>"""

POST_HTML = """<html><head>
<title>Fallback title</title>
<meta content="No, there is not going to be an agentic bank run" property="og:title">
<meta property="og:description" content="Why agents won&#39;t drain deposits overnight.">
<meta property="og:image" content="https://cdn.example.com/cover.png" />
<meta property="article:published_time" content="2026-10-02T07:30:00.000Z">
</head><body>...</body></html>"""


class _Resp:
    def __init__(self, content):
        self.content = content if isinstance(content, bytes) else content.encode()
        self.text = self.content.decode()

    def raise_for_status(self):
        pass


def test_all_ten_expert_newsletters_are_tracked():
    assert len(EXPERT_FEEDS) == 10
    assert all(f.region == "expert" for f in EXPERT_FEEDS)
    assert set(EXPERT_FEEDS) <= set(all_feeds())
    sitemap = {f.name for f in EXPERT_FEEDS if f.kind == "sitemap"}
    assert sitemap == {"Brainfood (Simon Taylor)",
                       "This Week in Fintech (Nik Milanović)"}


def test_parse_sitemap_keeps_only_posts():
    posts, children = fetcher._parse_sitemap(SITEMAP)
    assert children == []
    assert [u for u, _ in posts] == ["https://example.com/p/older-post",
                                     "https://example.com/p/agentic-bank-run"]
    assert posts[1][1] == datetime(2026, 10, 2, 8, tzinfo=timezone.utc)
    _, children = fetcher._parse_sitemap(SITEMAP_INDEX)
    assert children == ["https://example.com/sitemap-posts.xml"]


def test_page_meta_any_attribute_order_and_unescaped():
    meta = fetcher._page_meta(POST_HTML)
    assert meta["og:title"].startswith("No, there is not")
    assert meta["og:description"] == "Why agents won't drain deposits overnight."


def test_fetch_sitemap_feed_reads_newest_posts(monkeypatch):
    pages = {
        "https://example.com/sitemap.xml": SITEMAP_INDEX,
        "https://example.com/sitemap-posts.xml": SITEMAP,
        "https://example.com/p/agentic-bank-run": POST_HTML,
        "https://example.com/p/older-post": "<title>Older &amp; wiser</title>",
    }
    monkeypatch.setattr(fetcher.requests, "get",
                        lambda url, **k: _Resp(pages[url]))
    feed = Feed("TWIF", "https://example.com/sitemap.xml", "expert", "sitemap")
    arts = fetcher.fetch_feed(feed, timeout=5, max_per_feed=8)

    assert [a.title for a in arts] == [
        "No, there is not going to be an agentic bank run", "Older & wiser"]
    top = arts[0]
    assert top.region == "expert" and top.source == "TWIF"
    assert top.image_url == "https://cdn.example.com/cover.png"
    assert top.published == datetime(2026, 10, 2, 7, 30, tzinfo=timezone.utc)
    assert top.uid and top.uid != arts[1].uid
    # No published_time on the page: fall back to the sitemap's lastmod.
    assert arts[1].published == datetime(2026, 9, 1, 8, tzinfo=timezone.utc)


def test_sitemap_failure_is_skipped(monkeypatch):
    def boom(url, **k):
        raise fetcher.requests.ConnectionError("down")
    monkeypatch.setattr(fetcher.requests, "get", boom)
    feed = Feed("X", "https://example.com/sitemap.xml", "expert", "sitemap")
    assert fetcher.fetch_feed(feed, 5, 8) == []


def test_weakest_expert_post_outranks_strongest_news():
    best_news = classify(Article(
        title="Claude ChatGPT Gemini Qwen DeepSeek Grok agentic commerce launch",
        link="https://x/n", source="Anthropic", region="official",
        published=NOW - timedelta(hours=1)))
    assert best_news.category == CAT_AGENTIC
    weak_expert = classify(Article(
        title="Real-time payments in Asia Pacific", link="https://x/e",
        source="Agenda: Payments (Jeremy Light)", region="expert",
        published=NOW - timedelta(hours=23)))
    assert score_article(weak_expert) > score_article(best_news)


def _art(title, link, region="global", source="Src", hours=1):
    return Article(title=title, link=link, source=source, region=region,
                   uid=link, published=NOW - timedelta(hours=hours))


def test_expert_posts_survive_dedup_while_matching_news_is_dropped(tmp_path,
                                                             monkeypatch):
    store = SeenStore(str(tmp_path / "seen.json"))
    # The news itself was already shared a few hours ago.
    store.mark_titles(["Stripe buys OpenRouter for $8B"])
    feed = [
        _art("Stripe buys OpenRouter for $8B", "https://x/expert",
             region="expert", source="This Week in Fintech (Nik Milanović)"),
        _art("Stripe buys OpenRouter for $8B in AI deal", "https://x/news",
             source="TechCrunch AI"),
    ]
    monkeypatch.setattr(digest, "fetch_all", lambda *a, **k: list(feed))
    # Semantic pass flags both as stale and the news as a duplicate.
    monkeypatch.setattr(digest, "cluster_duplicates",
                        lambda arts, *a, **k: ({1: 0}, {0, 1}))
    cfg = Config(max_items=5, anthropic_api_key="k")
    picked = digest.select_articles(cfg, store, lookback_hours=24)
    assert [a.link for a in picked] == ["https://x/expert"]


def test_expert_badge_in_post():
    a = classify(Article(title="The Agentic Commerce Framework",
                         link="https://x/a", region="expert",
                         source="Payments Strategy Breakdown (Dwayne Gefferie)",
                         summary="A framework."))
    post = render_post(a)
    assert "✍️ Expert analysis" in post
    assert "Dwayne Gefferie" in post
