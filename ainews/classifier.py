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
]


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


def is_agentic(text: str) -> bool:
    return any(p.search(text) for p in _AGENTIC_PATS)


def classify(article: Article) -> Article:
    """Set ``article.platforms`` and ``article.category`` in place."""
    text = f"{article.title}\n{article.summary}"
    article.platforms = detect_platforms(text)

    if is_agentic(text):
        article.category = CAT_AGENTIC
    elif article.platforms:
        article.category = CAT_PLATFORM
    else:
        article.category = CAT_INDUSTRY
    return article
