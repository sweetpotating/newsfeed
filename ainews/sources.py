"""Curated AI news feeds.

Coverage spans three groups the user asked for:
  1. AI platforms  -> official blogs/newsrooms (Claude, ChatGPT, Gemini, Qwen,
     DeepSeek, Grok, plus other major labs) where a feed is published.
  2. AI industry   -> reputable global tech press + Asia-focused outlets.
  3. Agentic payments & commerce -> fintech/payments outlets that track this.

Notes
-----
* Not every AI lab publishes a stable RSS/Atom feed. Where an official feed
  is unreliable (e.g. DeepSeek), platform coverage is still captured because
  ``classifier.py`` tags items from the industry feeds by platform keyword.
* Dead or rate-limited feeds are skipped gracefully by the fetcher, so it is
  safe to keep optimistic entries here.

Region is used only for a small label in the digest:
  ``official`` = first-party lab blog, ``asia`` = Asia-focused, ``global`` =
  international press.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    region: str = "global"  # global | asia | official


# --- Official AI platform / lab feeds -------------------------------------
OFFICIAL_FEEDS = [
    # Claude / Anthropic
    Feed("Anthropic News", "https://www.anthropic.com/rss.xml", "official"),
    # ChatGPT / OpenAI
    Feed("OpenAI News", "https://openai.com/news/rss.xml", "official"),
    # Gemini / Google
    Feed("Google – Gemini", "https://blog.google/products/gemini/rss/", "official"),
    Feed("Google – The Keyword (AI)", "https://blog.google/technology/ai/rss/", "official"),
    Feed("Google DeepMind", "https://deepmind.google/blog/rss.xml", "official"),
    # Qwen / Alibaba
    Feed("Qwen (QwenLM)", "https://qwenlm.github.io/blog/index.xml", "official"),
    # Grok / xAI
    Feed("xAI News", "https://x.ai/news/rss.xml", "official"),
    # Other major labs / platforms
    Feed("Meta AI", "https://ai.meta.com/blog/rss/", "official"),
    Feed("Microsoft AI Blog", "https://blogs.microsoft.com/ai/feed/", "official"),
    Feed("Mistral AI", "https://mistral.ai/news/feed.xml", "official"),
    Feed("Hugging Face Blog", "https://huggingface.co/blog/feed.xml", "official"),
    Feed("Stability AI", "https://stability.ai/news?format=rss", "official"),
]

# --- Global / international AI industry press ------------------------------
GLOBAL_FEEDS = [
    Feed("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/", "global"),
    Feed("VentureBeat AI", "https://venturebeat.com/category/ai/feed/", "global"),
    Feed("The Verge – AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "global"),
    Feed("Ars Technica – AI", "https://arstechnica.com/ai/feed/", "global"),
    Feed("Wired – AI", "https://www.wired.com/feed/tag/ai/latest/rss", "global"),
    Feed("MIT Tech Review – AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed", "global"),
    Feed("The Decoder", "https://the-decoder.com/feed/", "global"),
    Feed("MarkTechPost", "https://www.marktechpost.com/feed/", "global"),
    Feed("Simon Willison", "https://simonwillison.net/atom/everything/", "global"),
    Feed("Google Research", "https://research.google/blog/rss/", "global"),
]

# --- Asia-focused tech coverage -------------------------------------------
ASIA_FEEDS = [
    Feed("SCMP – Tech", "https://www.scmp.com/rss/36/feed", "asia"),
    Feed("TechNode (China)", "https://technode.com/feed/", "asia"),
    Feed("Pandaily (China)", "https://pandaily.com/feed/", "asia"),
    Feed("KrASIA", "https://kr-asia.com/feed", "asia"),
    Feed("Analytics India Magazine", "https://analyticsindiamag.com/feed/", "asia"),
    Feed("The Register – AI/ML", "https://www.theregister.com/software/ai_ml/headlines.atom", "global"),
]

# --- Agentic payments & agentic commerce ----------------------------------
# No outlet has a pure "agentic commerce" feed, so we pull payments/fintech
# feeds and let the classifier surface the agentic items by keyword.
AGENTIC_FEEDS = [
    Feed("PYMNTS", "https://www.pymnts.com/feed/", "global"),
    Feed("Finextra", "https://www.finextra.com/rss/headlines.aspx", "global"),
    Feed("TechCrunch Fintech", "https://techcrunch.com/category/fintech/feed/", "global"),
]


def all_feeds() -> list[Feed]:
    return [*OFFICIAL_FEEDS, *GLOBAL_FEEDS, *ASIA_FEEDS, *AGENTIC_FEEDS]
