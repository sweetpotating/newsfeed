"""Classify articles into categories and tag the AI platform(s) they mention.

Two outputs per article:
  * ``platforms`` – list of detected platform keys, in priority order.
  * ``category``  – one of platforms / agentic / industry.

Assignment precedence: agentic > platform > industry. An article about, say,
"OpenAI agentic checkout" is genuinely an agentic-commerce story, so it lands
in the agentic bucket while *also* keeping its ``chatgpt`` platform tag for
the badge shown in the digest.
"""

from __future__ import annotations

import re
from typing import List

from .models import CAT_AGENTIC, CAT_INDUSTRY, CAT_PLATFORM, Article

# Platforms in the user's stated priority order. The order here drives both
# tag ordering and the order sections appear within the digest.
PLATFORM_ORDER = ["claude", "chatgpt", "gemini", "qwen", "deepseek", "grok"]

PLATFORM_LABELS = {
    "claude": "🟧 Claude",
    "chatgpt": "🟢 ChatGPT",
    "gemini": "🔵 Gemini",
    "qwen": "🟣 Qwen",
    "deepseek": "🐳 DeepSeek",
    "grok": "⚡ Grok",
}

# Keyword -> platform. Matched as whole words, case-insensitive.
_PLATFORM_KEYWORDS = {
    "claude": ["claude", "anthropic"],
    "chatgpt": ["chatgpt", "openai", "gpt-4", "gpt-4o", "gpt-5", "gpt 5",
                "o1", "o3", "o4-mini", "sora", "dall-e", "codex"],
    "gemini": ["gemini", "deepmind", "bard", "alphafold", "veo", "imagen", "gemma"],
    "qwen": ["qwen", "tongyi", "qwq"],
    "deepseek": ["deepseek"],
    "grok": ["grok", "xai", "x.ai"],
}

# Phrases that mark an item as agentic-payments / agentic-commerce.
_AGENTIC_KEYWORDS = [
    "agentic payment", "agentic payments", "agentic commerce",
    "agentic checkout", "agentic shopping", "agent payments",
    "agent-led commerce", "agent commerce", "ai agent payment",
    "autonomous payment", "autonomous checkout",
    "agent payments protocol", "ap2",
    "agentic commerce protocol", "x402",
    "intelligent commerce",          # Visa Intelligent Commerce
    "agent pay",                     # Mastercard Agent Pay
    "agent toolkit",                 # Stripe agent toolkit
    "pay with ai", "shopping agent", "checkout agent",
    "agentic banking", "agentic finance",
    # Standards for how agents identify themselves, sign in and buy.
    "agent protocol",                # Personal / Trusted / Agent Payments …
    "personal agent", "personal agents", "personal ai agent",
    "universal commerce protocol", "machine payments protocol",
    "agentic commerce experiences",  # Amex ACE
    "agent purchase protection",     # Amex
]

# A headline that mentions agents *and* buying, paying or a standard is about
# agentic commerce even without the exact phrases above, e.g. "Meta and
# Sierra announce open standard for AI agent interactions".
_AGENT_WORD = re.compile(r"(?<!\w)(ai\s+)?agent(s|ic)?(?!\w)", re.IGNORECASE)
_COMMERCE_WORD = re.compile(
    r"(?<!\w)(shop|shopping|shopper|shoppers|checkout|purchase|purchases|buy|"
    r"buying|buys|payment|payments|pay|merchant|merchants|commerce|retail|"
    r"retailer|retailers|card|cards|cardholder|protocol|standard|standards)"
    r"(?!\w)", re.IGNORECASE)

# Signals that a story is about AI at all. Used to keep general fintech or
# tech items (bank partnerships, charity savings accounts…) out of an AI feed.
_AI_WORD = re.compile(
    r"(?<!\w)(ai|a\.i\.|artificial intelligence|machine learning|llm|llms|"
    r"large language models?|genai|generative|chatbots?|agents?|agentic|"
    r"copilot|neural|deep learning|"
    r"(foundation|frontier|ai|image|video|world|language|reasoning|"
    r"open-weight|open|multimodal|embedding|diffusion) models?|"
    r"computer use|robots?|robotics|humanoids?|"
    r"mistral|llama|meta ai|hugging\s?face|perplexity|cohere|midjourney|"
    r"stable diffusion|nano banana|nvidia|gpus?)(?!\w)",
    re.IGNORECASE)

# Titles that are bare package release notes ("datasette-atom 0.11a0") or
# quote posts: low value in a news feed.
_LOW_VALUE_TITLE = re.compile(
    r"^([\w.\-]+\s+v?\d+(\.\d+)+[a-z0-9.]*|quoting\s.+)$", re.IGNORECASE)


def _compile(words: List[str]) -> List[re.Pattern]:
    pats = []
    for w in words:
        # Escape, then allow flexible whitespace; bound by non-word chars.
        esc = re.escape(w).replace(r"\ ", r"\s+")
        pats.append(re.compile(rf"(?<![\w]){esc}(?![\w])", re.IGNORECASE))
    return pats


_PLATFORM_PATS = {k: _compile(v) for k, v in _PLATFORM_KEYWORDS.items()}
_AGENTIC_PATS = _compile(_AGENTIC_KEYWORDS)


def detect_platforms(text: str) -> List[str]:
    found = [key for key, pats in _PLATFORM_PATS.items()
             if any(p.search(text) for p in pats)]
    # Return in priority order.
    return [k for k in PLATFORM_ORDER if k in found]


def is_agentic(text: str, title: str = "") -> bool:
    if any(p.search(text) for p in _AGENTIC_PATS):
        return True
    return bool(title and _AGENT_WORD.search(title)
                and _COMMERCE_WORD.search(title))


def is_ai_relevant(article: Article) -> bool:
    """True if the story is about AI (platform, agentic, AI wording, or from
    an AI lab's own blog)."""
    if (article.platforms or article.category == CAT_AGENTIC
            or article.region == "official"):
        return True
    return bool(_AI_WORD.search(f"{article.title}\n{article.summary}"))


def is_low_value(article: Article) -> bool:
    return bool(_LOW_VALUE_TITLE.match(article.title.strip()))


def classify(article: Article) -> Article:
    """Set ``article.platforms`` and ``article.category`` in place."""
    text = f"{article.title}\n{article.summary}"
    article.platforms = detect_platforms(text)

    if is_agentic(text, article.title):
        article.category = CAT_AGENTIC
    elif article.platforms:
        article.category = CAT_PLATFORM
    else:
        article.category = CAT_INDUSTRY
    return article
