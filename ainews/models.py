"""Shared data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

# Top-level categories an article can be sorted into.
CAT_PLATFORM = "platforms"
CAT_AGENTIC = "agentic"
CAT_INDUSTRY = "industry"


@dataclass
class Article:
    title: str
    link: str
    source: str
    region: str = "global"          # global | asia | official
    published: Optional[datetime] = None
    summary: str = ""
    uid: str = ""
    category: str = CAT_INDUSTRY
    platforms: List[str] = field(default_factory=list)
    image_url: Optional[str] = None     # best image pulled from the feed entry
    takeaways: List[str] = field(default_factory=list)  # AI-generated, may be empty
    also_in: List[str] = field(default_factory=list)     # other outlets on the same story
    score: float = 0.0                  # relevance score, set during ranking

    @property
    def sort_key(self) -> datetime:
        """A timezone-aware datetime usable for sorting newest-first.

        Items without a parseable date fall to the bottom (epoch).
        """
        return self.published or datetime.fromtimestamp(0, tz=timezone.utc)
