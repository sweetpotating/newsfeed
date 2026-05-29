"""Offline tests for summarizer degradation and feed image extraction."""

import feedparser

from ainews.fetcher import _entry_to_article
from ainews.models import Article
from ainews.sources import Feed
from ainews.summarizer import _build_payload, summarize


def test_summarize_no_api_key_is_noop():
    arts = [Article(title="t", link="https://x/y", source="s")]
    # Empty key -> graceful skip, no exception, takeaways stay empty.
    summarize(arts, api_key="", model="claude-haiku-4-5")
    assert arts[0].takeaways == []


def test_summarize_empty_list_is_noop():
    summarize([], api_key="key", model="claude-haiku-4-5")  # must not raise


def test_build_payload_shapes_articles():
    import json
    arts = [
        Article(title="Headline A", link="https://x/a", source="Src A",
                summary="blurb a"),
        Article(title="Headline B", link="https://x/b", source="Src B"),
    ]
    payload = json.loads(_build_payload(arts))
    assert len(payload["articles"]) == 2
    assert payload["articles"][0]["id"] == 0
    assert payload["articles"][0]["headline"] == "Headline A"
    # Missing blurb is given a placeholder, never dropped.
    assert payload["articles"][1]["blurb"]


MEDIA_RSS = b"""<?xml version="1.0"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel><title>F</title>
    <item>
      <title>With media:content</title>
      <link>https://example.com/1</link>
      <media:content url="https://img.example.com/lead.jpg" medium="image"/>
    </item>
    <item>
      <title>With img in summary</title>
      <link>https://example.com/2</link>
      <description>&lt;p&gt;&lt;img src="https://img.example.com/inline.png"/&gt;Hi&lt;/p&gt;</description>
    </item>
    <item>
      <title>No image</title>
      <link>https://example.com/3</link>
      <description>Just text, no picture.</description>
    </item>
  </channel>
</rss>
"""


def test_image_extraction_from_feed():
    parsed = feedparser.parse(MEDIA_RSS)
    feed = Feed("F", "https://example.com/feed", "global")
    arts = [_entry_to_article(e, feed) for e in parsed.entries]
    assert arts[0].image_url == "https://img.example.com/lead.jpg"
    assert arts[1].image_url == "https://img.example.com/inline.png"
    assert arts[2].image_url is None
