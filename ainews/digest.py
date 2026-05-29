"""Compile and send the AI news digest.

Pipeline: fetch feeds -> normalise -> drop already-seen -> drop too-old ->
classify -> cap -> format -> send -> persist state.

Run:
    python -m ainews                 # fetch + send (needs Telegram env vars)
    python -m ainews --dry-run       # print to stdout, send nothing
    python -m ainews --lookback 48   # widen the time window for this run
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import List

from .classifier import classify
from .config import Config
from .fetcher import fetch_all
from .formatter import format_digest
from .models import Article
from .sources import all_feeds
from .state import SeenStore
from .telegram import TelegramClient

log = logging.getLogger("ainews")


def _dedupe(articles: List[Article]) -> List[Article]:
    """Collapse duplicate uids (same story from overlapping feeds)."""
    by_uid = {}
    for a in articles:
        if a.uid not in by_uid:
            by_uid[a.uid] = a
    return list(by_uid.values())


def select_articles(cfg: Config, store: SeenStore,
                    lookback_hours: int) -> List[Article]:
    raw = fetch_all(all_feeds(), cfg.timeout, cfg.max_per_feed)
    articles = _dedupe(raw)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    first_run = store.is_empty()

    fresh: List[Article] = []
    for art in articles:
        if store.is_seen(art.uid):
            continue
        # Keep undated items only on a normal run within caps; always respect
        # the time window when we have a date.
        if art.published is not None and art.published < cutoff:
            continue
        fresh.append(classify(art))

    # Newest first overall, then apply the global cap.
    fresh.sort(key=lambda a: a.sort_key, reverse=True)

    if first_run:
        log.info("First run: empty state, capping starter digest.")
    return fresh[: cfg.max_items]


def run(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ainews", description="Send an AI news digest to Telegram."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the digest to stdout; do not send or save state.")
    parser.add_argument("--lookback", type=int, default=None,
                        help="Override lookback window in hours.")
    parser.add_argument("--max-items", type=int, default=None,
                        help="Override the max number of items in the digest.")
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

    # An empty/no-op store when --no-state, so nothing is read or written.
    store = SeenStore(
        cfg.state_file if not args.no_state else "/dev/null",
        ttl_days=cfg.state_ttl_days,
    )

    articles = select_articles(cfg, store, lookback)
    if not articles:
        log.info("No new articles within the last %dh. Nothing to send.", lookback)
        return 0

    messages = format_digest(articles)
    log.info("Prepared %d message(s) covering %d article(s).",
             len(messages), len(articles))

    if args.dry_run:
        for i, msg in enumerate(messages, 1):
            print(f"\n===== MESSAGE {i}/{len(messages)} =====\n{msg}")
        return 0

    client = TelegramClient(cfg.bot_token, cfg.chat_id, timeout=cfg.timeout)
    sent = client.send_all(messages)
    log.info("Sent %d message(s) to Telegram.", sent)

    if not args.no_state:
        store.mark(a.uid for a in articles)
        store.save()
        log.info("State updated: %s", cfg.state_file)
    return 0


if __name__ == "__main__":
    sys.exit(run())
