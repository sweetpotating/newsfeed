"""Shared data structures for the AI jobs bot."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    uid: str
    # Whether this company is one of the user's priority AI labs.
    is_priority_lab: bool = False
    department: str = ""
    posted: Optional[datetime] = None
    summary: str = ""              # short plain-text blurb from the posting
    role_tags: List[str] = field(default_factory=list)  # research, ml, data, …
    score: float = 0.0            # relevance score, set during ranking

    @property
    def sort_key(self) -> datetime:
        """Timezone-aware datetime for newest-first sorting.

        Postings without a parseable date fall to the bottom (epoch).
        """
        return self.posted or datetime.fromtimestamp(0, tz=timezone.utc)
