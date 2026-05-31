"""Persistent de-duplication state.

A tiny JSON file maps ``uid -> unix timestamp first seen``. It is committed
back to the repo by the GitHub Action so the next scheduled run knows what it
already sent. Entries older than the TTL are pruned to keep the file small.
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, Iterable


class SeenStore:
    def __init__(self, path: str, ttl_days: int = 90):
        self.path = path
        self.ttl_seconds = ttl_days * 86400
        self._seen: Dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            ids = data.get("ids", {}) if isinstance(data, dict) else {}
            self._seen = {k: float(v) for k, v in ids.items()}
        except (json.JSONDecodeError, ValueError, OSError):
            self._seen = {}

    def is_seen(self, uid: str) -> bool:
        return uid in self._seen

    def is_empty(self) -> bool:
        return not self._seen

    def mark(self, uids: Iterable[str]) -> None:
        now = time.time()
        for uid in uids:
            self._seen.setdefault(uid, now)

    def prune(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        self._seen = {k: v for k, v in self._seen.items() if v >= cutoff}

    def save(self) -> None:
        self.prune()
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = f"{self.path}.tmp"
        payload = {"updated": int(time.time()), "ids": self._seen}
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=0, sort_keys=True)
        os.replace(tmp, self.path)
