"""End-to-end-ish test of the feed parsing -> classify -> format chain.

Runs offline: it feeds a real RSS document (bytes) through the same parsing
path the fetcher uses, so the normalisation, classification and rendering are
all exercised without any network.
"""

import feedparser

from ainews.classifier import classify
from ainews.fetcher import _entry_to_article
from ainews.formatter import format_digest
from ainews.sources import Feed

SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample AI Feed</title>
    <item>
      <title>Anthropic releases Claude Opus 4.8</title>
      <link>https://example.com/claude?utm_source=rss&amp;id=1</link>
      <description>The new &lt;b&gt;Claude&lt;/b&gt; model tops benchmarks.</description>
      <pubDate>Wed, 28 May 2026 10:00:00 GMT</pubDate>
      <guid>https://example.com/claude</guid>
    </item>
    <item>
      <title>Visa launches Intelligent Commerce for AI agents</title>
      <link>https://example.com/visa-agentic</link>
      <description>Agentic commerce checkout arrives.</description>
      <pubDate>Wed, 28 May 2026 09:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Startup raises Series B for data labeling</title>
      <link>https://example.com/startup</link>
      <description>Generic industry funding news.</description>
      <pubDate>Wed, 28 May 2026 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def _parse_sample():
    parsed = feedparser.parse(SAMPLE_RSS)
    feed = Feed("Sample AI Feed", "https://example.com/feed", "global")
    arts = [_entry_to_article(e, feed) for e in parsed.entries]
    return [classify(a) for a in arts if a]


def test_parse_normalises_entries():
    arts = _parse_sample()
    assert len(arts) == 3
    claude = arts[0]
    # Tracking param stripped from the uid basis; title/summary cleaned of HTML.
    assert claude.title == "Anthropic releases Claude Opus 4.8"
    assert "<b>" not in claude.summary and "Claude" in claude.summary
    assert claude.published is not None
    assert claude.uid  # non-empty stable id


def test_full_chain_categories_and_render():
    arts = _parse_sample()
    cats = {a.category for a in arts}
    assert cats == {"platforms", "agentic", "industry"}

    msgs = format_digest(arts)
    blob = "\n".join(msgs)
    assert "AI News Digest" in blob
    assert "Claude" in blob
    assert "Intelligent Commerce" in blob
    # The agentic item must land in the agentic section, not platforms.
    assert blob.index("Agentic Payments") < blob.index("Intelligent Commerce")
