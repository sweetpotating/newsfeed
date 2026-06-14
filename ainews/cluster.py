"""Semantic near-duplicate clustering of headlines via the Claude API.

Lexical overlap (``ainews.similar``) catches reworded-but-similar headlines,
but misses different *framings* of the same story — e.g. "US forces Anthropic
to suspend Fable" vs "Anthropic cuts off Fable access following government
order" vs "Amazon research led to the White House's Anthropic ban". These share
few words yet report one event.

This module asks Claude to group candidate articles that report the SAME
underlying story — within the batch and against what was shared in the last
24h — so the channel/bot share each story once (and can note the other outlets
that covered it). It degrades gracefully: missing key/SDK, or a failed or
unparseable call, returns "no opinion", leaving the caller's lexical result
untouched.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List, Set, Tuple

from .models import Article

log = logging.getLogger("ainews.cluster")

_SYSTEM = (
    "You de-duplicate an AI-news feed. You are given candidate articles (each "
    "with an id, headline and source) and a list of headlines already shared "
    "in the last 24 hours. For each candidate decide whether it reports the "
    "SAME underlying story as (a) an already-shared headline, or (b) an earlier "
    "candidate in the list.\n\n"
    "Rules:\n"
    "- Same story = the same core event/announcement, even across different "
    "outlets or angles, follow-ups, or reactions to that one event.\n"
    "- Different stories = genuinely separate developments (a model launch vs. "
    "a lawsuit about it; two different companies' news), even if the companies "
    "or topic overlap.\n"
    "- When unsure, treat it as NOT a duplicate.\n"
    "- 'same_as_candidate_id' must reference an EARLIER candidate id (smaller "
    "number) or be null.\n"
    "Return the structured output."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "duplicate_of_recent": {"type": "boolean"},
                    "same_as_candidate_id": {"type": ["integer", "null"]},
                },
                "required": ["id", "duplicate_of_recent",
                             "same_as_candidate_id"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _parse_decisions(data: dict, n: int) -> Tuple[Dict[int, int], Set[int]]:
    """Turn the model's JSON into (rep_of, stale).

    rep_of[i] = j (j < i): candidate i is the same story as earlier candidate j.
    stale: candidate indices that duplicate a story shared in the last 24h.
    """
    rep_of: Dict[int, int] = {}
    stale: Set[int] = set()
    for entry in (data.get("items", []) if isinstance(data, dict) else []):
        try:
            i = int(entry["id"])
        except (KeyError, ValueError, TypeError):
            continue
        if not (0 <= i < n):
            continue
        if entry.get("duplicate_of_recent"):
            stale.add(i)
        same = entry.get("same_as_candidate_id")
        if same is not None:
            try:
                j = int(same)
            except (ValueError, TypeError):
                continue
            if 0 <= j < i:                 # must reference an earlier candidate
                rep_of[i] = j
    return rep_of, stale


def cluster_duplicates(articles: List[Article], recent_titles: List[str],
                       api_key: str, model: str,
                       timeout: int = 60) -> Tuple[Dict[int, int], Set[int]]:
    """Group same-story candidates. Returns (rep_of, stale); empty on failure."""
    if len(articles) < 2 and not recent_titles:
        return {}, set()
    try:
        import anthropic
    except ImportError:
        return {}, set()
    if not api_key:
        return {}, set()

    payload = {
        "candidates": [
            {"id": i, "headline": a.title, "source": a.source}
            for i, a in enumerate(articles)
        ],
        "recent_headlines": list(recent_titles)[:80],
    }
    client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=2000,
            system=[{
                "type": "text",
                "text": _SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": "De-duplicate these.\n\n"
                + json.dumps(payload, ensure_ascii=False),
            }],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
    except Exception as exc:  # any API/network/SDK error -> graceful skip
        log.warning("Dedup clustering failed (%s); using lexical result.", exc)
        return {}, set()

    try:
        text = next(b.text for b in resp.content if b.type == "text")
        data = json.loads(text)
    except (StopIteration, ValueError, json.JSONDecodeError) as exc:
        log.warning("Could not parse dedup response (%s).", exc)
        return {}, set()

    rep_of, stale = _parse_decisions(data, len(articles))
    log.info("Semantic dedup over %d candidate(s): %d stale, %d in-batch dup(s).",
             len(articles), len(stale), len(rep_of))
    return rep_of, stale
