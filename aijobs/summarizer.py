"""Generate a one-line "what this role is" note per job using the Claude API.

All jobs in a run are summarized in a *single* batched request to keep cost
and latency low: the stable instructions sit in a cached system prompt, and
the per-run job list is the only varying part. Each job is keyed by its index
so results map back unambiguously.

Best-effort: if the Anthropic SDK / API key is unavailable, or the call fails,
this degrades gracefully — jobs keep their existing (possibly empty) summary
and the formatter falls back to whatever blurb the ATS provided.
"""

from __future__ import annotations

import json
import logging
from typing import List

from .models import Job

log = logging.getLogger("aijobs.summarizer")

_SYSTEM = (
    "You write a single concise note for each AI/ML job opening, for a reader "
    "hunting for AI roles in Singapore. For each job you get a numeric id, a "
    "title, the company, the location, and (sometimes) a short blurb.\n\n"
    "For each job, write ONE sentence (under ~22 words) that says what the role "
    "is and who it suits — concrete and specific, no hype, no marketing "
    "language, no emoji. Base it ONLY on the provided fields; do not invent "
    "facts, requirements, salary, or team details not present. If you have "
    "nothing beyond the title, paraphrase the title plainly.\n\n"
    "Return your answer using the provided structured output schema."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "jobs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "note": {"type": "string"},
                },
                "required": ["id", "note"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["jobs"],
    "additionalProperties": False,
}


def _build_payload(jobs: List[Job]) -> str:
    items = []
    for i, j in enumerate(jobs):
        items.append({
            "id": i,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "blurb": j.summary or "(no blurb provided)",
        })
    return json.dumps({"jobs": items}, ensure_ascii=False)


def summarize(jobs: List[Job], api_key: str, model: str,
              timeout: int = 60) -> None:
    """Populate ``job.summary`` with a one-liner in place. Never raises."""
    if not jobs:
        return
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK not installed; skipping AI notes.")
        return
    if not api_key:
        log.info("No ANTHROPIC_API_KEY set; skipping AI notes.")
        return

    client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
    payload = _build_payload(jobs)

    try:
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
                    "Write one note per job. Return one entry per id.\n\n"
                    + payload
                ),
            }],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
    except Exception as exc:
        log.warning("Summarization failed (%s); continuing without notes.", exc)
        return

    try:
        text = next(b.text for b in resp.content if b.type == "text")
        data = json.loads(text)
    except (StopIteration, ValueError, json.JSONDecodeError) as exc:
        log.warning("Could not parse summary response (%s).", exc)
        return

    by_id = {}
    for entry in data.get("jobs", []):
        try:
            by_id[int(entry["id"])] = str(entry.get("note", "")).strip()
        except (KeyError, ValueError, TypeError):
            continue

    for i, job in enumerate(jobs):
        note = by_id.get(i)
        if note:
            job.summary = note

    cache_read = getattr(resp.usage, "cache_read_input_tokens", 0)
    log.info(
        "Generated notes for %d/%d jobs (model=%s, in=%s out=%s cache_read=%s).",
        sum(1 for j in jobs if j.summary), len(jobs), model,
        resp.usage.input_tokens, resp.usage.output_tokens, cache_read,
    )
