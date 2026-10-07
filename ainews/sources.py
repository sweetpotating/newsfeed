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

Region drives a small label in the digest:
  ``official`` = first-party lab blog, ``asia`` = Asia-focused, ``global`` =
  international press, ``expert`` = hand-picked analyst newsletters (these
  also rank first; see ``ranker.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    region: str = "global"  # global | asia | official | expert
    # "rss" for RSS/Atom; "sitemap" for sites without a public feed (beehiiv),
    # where posts are listed from sitemap.xml and read from each post's page;
    # "gnews" for a Google News search feed (RSS with outlet-suffixed titles).
    kind: str = "rss"
    # For "sitemap": only URLs whose path starts with this are posts.
    path: str = "/p/"


def _gnews(name: str, query: str) -> Feed:
    """A Google News search feed: catches press releases and coverage from
    every outlet, including company newsrooms with no feed of their own."""
    return Feed(f"Google News: {name}",
                "https://news.google.com/rss/search?q="
                + quote_plus(f"{query} when:1d")
                + "&hl=en-US&gl=US&ceid=US:en",
                "global", "gnews")


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


# --- Expert fintech & payments newsletters -----------------------------------
# Long-form analysis (agentic commerce, PSP economics, payment architecture,
# stablecoins). They publish weekly or less, so every new post is surfaced.
EXPERT_FEEDS = [
    # Agentic commerce, protocols, stablecoins.
    Feed("Brainfood (Simon Taylor)",
         "https://www.fintechbrainfood.com/sitemap.xml", "expert", "sitemap"),
    # Agentic commerce and the PSP stack, from a product operator.
    Feed("Fintech: Under the Hood (Jas Shah)",
         "https://jasshah.substack.com/feed", "expert"),
    # AI agents and machine-to-machine money; crypto/investor lens.
    Feed("Fintech Blueprint (Lex Sokolin)",
         "https://lex.substack.com/feed", "expert"),
    # Strategy breakdowns of Stripe, Adyen, Airwallex and other PSPs.
    Feed("Payments Strategy Breakdown (Dwayne Gefferie)",
         "https://dwaynegefferie.substack.com/feed", "expert"),
    # Payment architecture; a sceptical take on agentic payments.
    Feed("Agenda: Payments (Jeremy Light)",
         "https://jeremylight.substack.com/feed", "expert"),
    # Payments strategy.
    Feed("Payments Culture (Matt Jones)",
         "https://www.paymentsculture.com/feed", "expert"),
    # PSP economics: how paytech makes money.
    Feed("Business of Payments (Geoffrey Barraclough)",
         "https://businessofpayments.substack.com/feed", "expert"),
    # Risk and regulation counterweight.
    Feed("Fintech Business Weekly (Jason Mikula)",
         "https://fintechbusinessweekly.substack.com/feed", "expert"),
    # Broad weekly fintech news and deals.
    Feed("This Week in Fintech (Nik Milanović)",
         "https://www.thisweekinfintech.com/sitemap.xml", "expert", "sitemap"),
    # Broader fintech balance.
    Feed("Fintech Takes (Alex Johnson)",
         "https://newsletter.fintechtakes.com/feed", "expert"),
]


# --- Breaking-news watch -----------------------------------------------------
# Company announcements often go out only as wire press releases or on the
# company's own blog (e.g. Amex's agentic commerce playbook on Business Wire,
# Sierra's Personal Agent Protocol on sierra.ai), which none of the outlet
# feeds above carry. Search feeds and first-party blogs close that gap.
WATCH_FEEDS = [
    _gnews("agentic commerce",
           '"agentic commerce" OR "agentic payments" OR "agentic checkout"'),
    _gnews("agent protocols",
           '"agent protocol" OR "personal agent" OR "Agent Pay" '
           'OR "Trusted Agent Protocol" OR "Agent Payments Protocol"'),
    _gnews("payment networks & AI agents",
           '("American Express" OR Amex OR Visa OR Mastercard OR Stripe '
           'OR Adyen OR PayPal OR Airwallex) ("AI agent" OR "AI agents" '
           'OR agentic)'),
    _gnews("Sierra", '"Sierra" ("Bret Taylor" OR "AI agent" OR agents)'),
    Feed("Sierra Blog", "https://sierra.ai/sitemap.xml", "official",
         "sitemap", path="/blog/"),
    Feed("Stripe Blog", "https://stripe.com/blog/feed.rss", "official"),
    Feed("The Verge", "https://www.theverge.com/rss/index.xml", "global"),
    Feed("CNBC Tech",
         "https://www.cnbc.com/id/19854910/device/rss/rss.html", "global"),
]


def all_feeds() -> list[Feed]:
    return [*OFFICIAL_FEEDS, *GLOBAL_FEEDS, *ASIA_FEEDS, *AGENTIC_FEEDS,
            *EXPERT_FEEDS, *WATCH_FEEDS]
