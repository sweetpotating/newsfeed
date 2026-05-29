"""Generate 3 concise takeaways per article using the Claude API.

All articles in a run are summarized in a *single* batched request to keep
cost and latency low: the stable instructions sit in a cached system prompt,
and the per-run article list is the only varying part. Each article is keyed
by its uid so results map back unambiguously.

Summaries are derived from the headline + the feed's summary blurb (no
full-page fetch). If the Anthropic SDK or API key is unavailable, or the call
fails, summarization degrades gracefully — articles keep an empty
``takeaways`` list and the formatter falls back to the plain blurb.
"""

from __future__ import annotations

import json
import logging
from typing import List

from .models import Article

log = logging.getLogger("ainews.summarizer")

_SYSTEM = (
    "You write concise, factual news takeaways for a busy reader who follows "
    "AI closely. For each article you are given a numeric id, a headline, the "
    "source, and a short summary blurb from the article's feed.\n\n"
    "For each article, produce exactly 3 short takeaway bullets:\n"
    "- Each bullet is one sentence, under ~20 words, concrete and specific.\n"
    "- Lead with the substance (what happened, what's new, why it matters).\n"
    "- No fluff, no hype, no marketing language, no emoji.\n"
    "- Base bullets ONLY on the provided headline and blurb. Do not invent "
    "facts, numbers, or quotes that aren't supported by the input. If the "
    "blurb is thin, write fewer, more general bullets rather than fabricating.\n\n"
    "Return your answer using the provided structured output schema."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "articles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "takeaways": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["id", "takeaways"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["articles"],
    "additionalProperties": False,
}


def _build_payload(articles: List[Article]) -> str:
    items = []
    for i, a in enumerate(articles):
        items.append(
            {
                "id": i,
                "headline": a.title,
                "source": a.source,
                "blurb": a.summary or "(no summary provided)",
            }
        )
    return json.dumps({"articles": items}, ensure_ascii=False)


def summarize(articles: List[Article], api_key: str, model: str,
              timeout: int = 60) -> None:
    """Populate ``article.takeaways`` in place. Best-effort; never raises."""
    if not articles:
        return
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK not installed; skipping AI takeaways.")
        return
    if not api_key:
        log.info("No ANTHROPIC_API_KEY set; skipping AI takeaways.")
        return

    client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
    payload = _build_payload(articles)

    try:
        # Single batched call. The system prompt is stable across runs, so it
        # caches; only the article list (last user block) varies.
        resp = client.messages.create(
            model=model,
            max_tokens=4000,
            system=[{
                "type": "text",
                "text": _SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": (
                    "Summarize these articles. Return one entry per id.\n\n"
                    + payload
                ),
            }],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
    except Exception as exc:  # any API/network/SDK error -> graceful skip
        log.warning("Summarization failed (%s); continuing without takeaways.", exc)
        return

    try:
        text = next(b.text for b in resp.content if b.type == "text")
        data = json.loads(text)
    except (StopIteration, ValueError, json.JSONDecodeError) as exc:
        log.warning("Could not parse summary response (%s).", exc)
        return

    by_id = {}
    for entry in data.get("articles", []):
        try:
            by_id[int(entry["id"])] = [
                str(t).strip() for t in entry.get("takeaways", []) if str(t).strip()
            ]
        except (KeyError, ValueError, TypeError):
            continue

    for i, art in enumerate(articles):
        art.takeaways = by_id.get(i, [])[:3]

    cache_read = getattr(resp.usage, "cache_read_input_tokens", 0)
    log.info(
        "Generated takeaways for %d/%d articles (model=%s, in=%s out=%s cache_read=%s).",
        sum(1 for a in articles if a.takeaways), len(articles), model,
        resp.usage.input_tokens, resp.usage.output_tokens, cache_read,
    )
