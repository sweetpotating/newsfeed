"""Persistent de-duplication state.

A tiny JSON file maps ``uid -> unix timestamp first seen``, plus the titles of
recently sent stories so near-duplicates from other outlets can be skipped.
It is committed back to the repo by the GitHub Action so the next scheduled
run knows what it already sent. Entries older than the TTL are pruned to keep
the file small.
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, FrozenSet, Iterable, List

from .similar import title_tokens

# Titles only matter for the "same story, different outlet" window; keep them
# a little longer than the matching window so clock skew can't drop them early.
TITLE_TTL_SECONDS = 2 * 86400
# How far back a previously sent title blocks a similar new one.
TITLE_MATCH_WINDOW_SECONDS = 86400


class SeenStore:
    def __init__(self, path: str, ttl_days: int = 45):
        self.path = path
        self.ttl_seconds = ttl_days * 86400
        self._seen: Dict[str, float] = {}
        self._titles: Dict[str, float] = {}   # raw title -> unix ts sent
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            ids = data.get("ids", {}) if isinstance(data, dict) else {}
            self._seen = {k: float(v) for k, v in ids.items()}
            titles = data.get("titles", {}) if isinstance(data, dict) else {}
            if isinstance(titles, dict):
                self._titles = {str(k): float(v) for k, v in titles.items()}
        except (json.JSONDecodeError, ValueError, OSError):
            # Corrupt/empty state should never crash a run.
            self._seen = {}
            self._titles = {}

    def is_seen(self, uid: str) -> bool:
        return uid in self._seen

    def is_empty(self) -> bool:
        return not self._seen

    def mark(self, uids: Iterable[str]) -> None:
        now = time.time()
        for uid in uids:
            self._seen.setdefault(uid, now)

    def mark_titles(self, titles: Iterable[str]) -> None:
        now = time.time()
        for title in titles:
            if title:
                self._titles.setdefault(title, now)

    def recent_title_tokens(
        self, window_seconds: int = TITLE_MATCH_WINDOW_SECONDS
    ) -> List[FrozenSet[str]]:
        """Token sets of titles sent within the window (for similarity dedup)."""
        cutoff = time.time() - window_seconds
        return [title_tokens(t) for t, ts in self._titles.items() if ts >= cutoff]

    def prune(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        self._seen = {k: v for k, v in self._seen.items() if v >= cutoff}
        title_cutoff = time.time() - TITLE_TTL_SECONDS
        self._titles = {k: v for k, v in self._titles.items()
                        if v >= title_cutoff}

    def save(self) -> None:
        self.prune()
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = f"{self.path}.tmp"
        payload = {
            "updated": int(time.time()),
            "ids": self._seen,
            "titles": self._titles,
        }
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=0, sort_keys=True)
        os.replace(tmp, self.path)
