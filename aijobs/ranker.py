"""Score and rank Singapore AI jobs so the feed stays focused.

With one Telegram message per role, sending everything new could flood the
chat. We score each posting and keep the top N. Scoring favours what the user
asked for: the marquee AI labs first (⭐), then research / ML-heavy roles, then
recency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from .models import Job

# Role-tag weights (highest signal first).
_ROLE_WEIGHTS = {
    "research": 6.0,
    "ai-safety": 5.0,
    "ml": 5.0,
    "infra": 4.0,
    "ai-product": 3.0,
    "data": 3.0,
}


def _recency_points(posted) -> float:
    if posted is None:
        return 0.0
    age_d = (datetime.now(timezone.utc) - posted).total_seconds() / 86400.0
    if age_d <= 3:
        return 6.0
    if age_d <= 7:
        return 4.0
    if age_d <= 21:
        return 2.0
    return 0.5


def score_job(j: Job) -> float:
    score = 0.0

    # Priority frontier labs are the headline ask — float them to the top.
    if j.is_priority_lab:
        score += 12.0

    # Best (highest-weight) role tag the posting carries.
    if j.role_tags:
        score += max(_ROLE_WEIGHTS.get(t, 1.0) for t in j.role_tags)
        # Small bonus for spanning multiple AI facets (e.g. research + infra).
        score += 0.5 * (len(j.role_tags) - 1)

    score += _recency_points(j.posted)
    return score


def rank(jobs: List[Job], limit: int) -> List[Job]:
    for j in jobs:
        j.score = score_job(j)
    ranked = sorted(jobs, key=lambda j: (j.score, j.sort_key), reverse=True)
    return ranked[:limit]
