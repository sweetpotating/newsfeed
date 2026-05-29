"""Score and rank articles so a one-post-per-article digest stays focused.

With one Telegram message per article, sending everything new would flood the
chat. We score each item by relevance and keep the top N. Scoring favours the
things the user cares about most: AI platforms (in priority order) and agentic
payments/commerce, then recency, with a nudge for official lab sources.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from .classifier import PLATFORM_ORDER
from .models import CAT_AGENTIC, CAT_PLATFORM, Article


def _recency_points(published) -> float:
    if published is None:
        return 0.0
    age_h = (datetime.now(timezone.utc) - published).total_seconds() / 3600.0
    if age_h <= 6:
        return 6.0
    if age_h <= 24:
        return 4.0
    if age_h <= 48:
        return 2.0
    return 0.5


def score_article(a: Article) -> float:
    score = 0.0

    # Category weight: platforms and agentic commerce are the headline asks.
    if a.category == CAT_AGENTIC:
        score += 10.0
    elif a.category == CAT_PLATFORM:
        score += 8.0
    else:
        score += 3.0

    # Platform priority: Claude > ChatGPT > Gemini > Qwen > DeepSeek > Grok.
    if a.platforms:
        idx = PLATFORM_ORDER.index(a.platforms[0])
        score += (len(PLATFORM_ORDER) - idx)  # 6 down to 1
        # Small bonus for covering multiple priority platforms at once.
        score += 0.5 * (len(a.platforms) - 1)

    # First-party announcements are high signal.
    if a.region == "official":
        score += 2.0

    score += _recency_points(a.published)
    return score


def rank(articles: List[Article], limit: int) -> List[Article]:
    for a in articles:
        a.score = score_article(a)
    ranked = sorted(
        articles,
        key=lambda a: (a.score, a.sort_key),
        reverse=True,
    )
    return ranked[:limit]
