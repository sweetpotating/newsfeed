"""Near-duplicate detection for story titles.

Different outlets cover the same story with slightly different headlines
("Google announces Gemini Live Translate" vs "Google's Gemini Live Translate
delivers real-time voice translation"). Exact uid dedup can't catch these, so
we compare titles as bags of meaningful words: high overlap means it's the
same story and we should only share it once.
"""

from __future__ import annotations

import re
from typing import FrozenSet, Iterable, List, Optional

# Words too common in headlines to signal story identity.
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "for",
    "from", "has", "have", "how", "in", "into", "is", "it", "its", "may",
    "more", "new", "now", "of", "on", "or", "out", "over", "say", "says",
    "that", "the", "their", "this", "to", "up", "what", "when", "why",
    "will", "with", "you", "your",
}

_WORD_RE = re.compile(r"[a-z0-9]+")


def _norm(word: str) -> str:
    # Fold plurals so "payments"/"payment" and "merchants"/"merchant" align.
    if len(word) >= 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def title_tokens(title: str) -> FrozenSet[str]:
    """Normalise a headline to its set of meaningful lowercase words."""
    words = _WORD_RE.findall(title.lower())
    return frozenset(_norm(w) for w in words
                     if w not in _STOPWORDS and len(w) > 1)


def is_similar(a: FrozenSet[str], b: FrozenSet[str],
               jaccard: float = 0.4, containment: float = 0.7) -> bool:
    """True if two token sets very likely describe the same story.

    Matches on either Jaccard overlap (balanced titles) or containment
    (a short headline whose words are nearly all inside a longer one).
    Thresholds are tuned on real duplicate headlines; very differently
    worded covers of the same story can still slip through.
    """
    if not a or not b:
        return False
    inter = len(a & b)
    if inter == 0:
        return False
    if inter / len(a | b) >= jaccard:
        return True
    return inter / min(len(a), len(b)) >= containment


def is_similar_to_any(tokens: FrozenSet[str],
                      seen: Iterable[FrozenSet[str]]) -> bool:
    return any(is_similar(tokens, s) for s in seen)


def first_similar_index(tokens: FrozenSet[str],
                        seen: List[FrozenSet[str]]) -> Optional[int]:
    """Index of the first token set similar to ``tokens``, else None."""
    for i, s in enumerate(seen):
        if is_similar(tokens, s):
            return i
    return None
