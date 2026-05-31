"""Compile and send the Singapore AI jobs feed.

Pipeline: fetch ATS boards -> keep Singapore AI roles -> drop already-seen ->
drop too-old -> rank -> cap -> (optional AI note) -> render -> send ->
persist state.

Run:
    python -m aijobs                 # fetch + send (needs Telegram env vars)
    python -m aijobs --dry-run       # print to stdout, send nothing
    python -m aijobs --lookback 336  # widen the time window for this run
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import List

from .config import Config
from .fetcher import fetch_all
from .filters import is_ai_role, is_singapore, role_tags
from .formatter import MAX_MSG_LEN, render_header, render_post
from .models import Job
from .ranker import rank
from .sources import all_companies
from .state import SeenStore
from .summarizer import summarize
from .telegram import TelegramClient

log = logging.getLogger("aijobs")


def _dedupe(jobs: List[Job]) -> List[Job]:
    by_uid = {}
    for j in jobs:
        if j.uid not in by_uid:
            by_uid[j.uid] = j
    return list(by_uid.values())


def select_jobs(cfg: Config, store: SeenStore, lookback_hours: int) -> List[Job]:
    raw = fetch_all(all_companies(), cfg.timeout)
    jobs = _dedupe(raw)

    extra = [k for k in cfg.extra_locations.split(",") if k.strip()]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    fresh: List[Job] = []
    sg_ai = 0
    for job in jobs:
        if not is_singapore(job.location, extra):
            continue
        if not is_ai_role(job.title, job.department):
            continue
        sg_ai += 1
        job.role_tags = role_tags(job.title, job.department)
        if store.is_seen(job.uid):
            continue
        # Respect the time window only when we have a posting date.
        if job.posted is not None and job.posted < cutoff:
            continue
        fresh.append(job)

    log.info("Singapore AI roles found: %d (%d new within window).",
             sg_ai, len(fresh))
    return rank(fresh, cfg.max_items)


def run(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aijobs",
        description="Send a feed of AI jobs in Singapore to Telegram.",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print to stdout; do not send or save state.")
    parser.add_argument("--lookback", type=int, default=None,
                        help="Override lookback window in hours.")
    parser.add_argument("--max-items", type=int, default=None,
                        help="Override the max number of jobs sent.")
    parser.add_argument("--no-state", action="store_true",
                        help="Do not read or write the dedup state file.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = Config.from_env()
    if args.max_items is not None:
        cfg.max_items = args.max_items
    lookback = args.lookback if args.lookback is not None else cfg.lookback_hours

    if not args.dry_run:
        cfg.require_telegram()

    store = SeenStore(
        cfg.state_file if not args.no_state else "/dev/null",
        ttl_days=cfg.state_ttl_days,
    )

    jobs = select_jobs(cfg, store, lookback)
    if not jobs:
        log.info("No new Singapore AI roles within the last %dh. Nothing to send.",
                 lookback)
        return 0

    if cfg.summarize:
        summarize(jobs, cfg.anthropic_api_key, cfg.summary_model,
                  timeout=max(cfg.timeout, 60))

    posts = [(j, render_post(j, max_len=MAX_MSG_LEN)) for j in jobs]
    log.info("Prepared %d post(s).", len(posts))

    if args.dry_run:
        print("\n" + render_header(len(posts)))
        for i, (job, text) in enumerate(posts, 1):
            print(f"\n===== JOB {i}/{len(posts)} (score={job.score:.1f}) =====\n{text}")
        return 0

    client = TelegramClient(cfg.bot_token, cfg.chat_id, timeout=cfg.timeout)

    # Lead with a small header so the batch reads as one digest.
    try:
        client.send_message(render_header(len(posts)))
    except RuntimeError as exc:
        log.warning("Failed to send header: %s", exc)
    time.sleep(cfg.send_delay)

    sent = 0
    sent_uids = []
    for job, text in posts:
        try:
            client.send_message(text, disable_preview=True)
            sent += 1
            sent_uids.append(job.uid)
        except RuntimeError as exc:
            log.warning("Failed to send post for %r: %s", job.title[:60], exc)
        time.sleep(cfg.send_delay)
    log.info("Sent %d/%d post(s) to Telegram.", sent, len(posts))

    if not args.no_state and sent_uids:
        store.mark(sent_uids)
        store.save()
        log.info("State updated: %s", cfg.state_file)
    return 0


if __name__ == "__main__":
    sys.exit(run())
