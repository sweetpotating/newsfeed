"""Persistent subscriber list.

Anyone who sends ``/start`` to the bot is added here; ``/stop`` (or blocking
the bot) removes them. The digest is delivered to everyone in this list. Like
the dedup state, the file is committed back to the repo by the GitHub Action so
the subscriber list survives between runs.

Shape on disk::

    {
      "updated": 1780000000,
      "offset": 123456789,            # last Telegram update_id processed
      "subscribers": {
        "111222333": {"first_name": "Alice", "username": "alice",
                       "joined": 1780000000}
      }
    }
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, List


class SubscriberStore:
    def __init__(self, path: str):
        self.path = path
        self._subs: Dict[str, dict] = {}
        self.offset: int = 0
        self._dirty = False
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, ValueError, OSError):
            # Corrupt/empty state should never crash a run.
            return
        if not isinstance(data, dict):
            return
        subs = data.get("subscribers", {})
        if isinstance(subs, dict):
            self._subs = {
                str(k): v for k, v in subs.items() if isinstance(v, dict)
            }
        try:
            self.offset = int(data.get("offset", 0))
        except (TypeError, ValueError):
            self.offset = 0

    # --- queries -----------------------------------------------------------
    def chat_ids(self) -> List[str]:
        return list(self._subs.keys())

    def count(self) -> int:
        return len(self._subs)

    def has(self, chat_id) -> bool:
        return str(chat_id) in self._subs

    @property
    def dirty(self) -> bool:
        return self._dirty

    # --- mutations ---------------------------------------------------------
    def add(self, chat_id, *, first_name: str = "", username: str = "") -> bool:
        """Add a subscriber. Returns True only if newly added."""
        cid = str(chat_id)
        if cid in self._subs:
            return False
        self._subs[cid] = {
            "first_name": first_name or "",
            "username": username or "",
            "joined": int(time.time()),
        }
        self._dirty = True
        return True

    def remove(self, chat_id) -> bool:
        """Remove a subscriber. Returns True if one was actually removed."""
        if self._subs.pop(str(chat_id), None) is not None:
            self._dirty = True
            return True
        return False

    def set_offset(self, offset: int) -> None:
        offset = int(offset)
        if offset != self.offset:
            self.offset = offset
            self._dirty = True

    # --- persistence -------------------------------------------------------
    def save(self) -> None:
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = f"{self.path}.tmp"
        payload = {
            "updated": int(time.time()),
            "offset": self.offset,
            "subscribers": self._subs,
        }
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=0, sort_keys=True)
        os.replace(tmp, self.path)
        self._dirty = False
