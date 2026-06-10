"""Cache the most recently sent digest so subscribers can replay it on demand.

The ``/latest`` command re-sends this batch to whoever asks, without
re-fetching feeds or calling the summariser — so it's cheap and works even
from the lightweight subscriber-poll workflow (which never touches the feeds).
"""

from __future__ import annotations

import json
import os
import time
from typing import List, Optional, Tuple

# A replayable post is just its rendered text and an optional photo url.
Post = Tuple[str, Optional[str]]


def save_last_digest(path: str, posts: List[Post]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    payload = {
        "generated": int(time.time()),
        "posts": [{"text": text, "photo": photo} for text, photo in posts],
    }
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=0)
    os.replace(tmp, path)


def load_last_digest(path: str) -> List[Post]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, ValueError, OSError):
        return []
    raw = data.get("posts", []) if isinstance(data, dict) else []
    posts: List[Post] = []
    for item in raw:
        if isinstance(item, dict) and item.get("text"):
            posts.append((item["text"], item.get("photo")))
    return posts
