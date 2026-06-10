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
import time
from datetime import datetime, timedelta, timezone
from typing import List

from .classifier import classify
from .config import Config
from .fetcher import fetch_all
from .formatter import MAX_CAPTION_LEN, MAX_MSG_LEN, render_post
from .lastdigest import save_last_digest
from .models import Article
from .ranker import rank
from .sources import all_feeds
from .state import SeenStore
from .subscribe import is_unreachable, sync_subscribers
from .subscribers import SubscriberStore
from .summarizer import summarize
from .telegram import TelegramClient

log = logging.getLogger("ainews")


def _dedupe(articles: List[Article]) -> List[Article]:
    """Collapse duplicate uids (same story from overlapping feeds)."""
    by_uid = {}
    for a in articles:
        if a.uid not in by_uid:
            by_uid[a.uid] = a
    return list(by_uid.values())


def _recipients(cfg: Config, subs: SubscriberStore) -> List[str]:
    """All chat ids to deliver to: every subscriber, plus the configured
    TELEGRAM_CHAT_ID (owner/channel) when set and not already subscribed."""
    recipients = subs.chat_ids()
    if cfg.chat_id and cfg.chat_id not in recipients:
        recipients = recipients + [cfg.chat_id]
    return recipients


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

    if first_run:
        log.info("First run: empty state, capping starter digest.")

    # Rank by relevance (platforms & agentic first, then recency) and keep the
    # top N so a one-post-per-article digest doesn't flood the chat.
    return rank(fresh, cfg.max_items)


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
    parser.add_argument("--sync-only", action="store_true",
                        help="Only process /start and /stop subscribers, then "
                             "exit. Does not fetch feeds or send a digest.")
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

    # The subscriber list drives delivery; processing it needs a live client.
    subs = SubscriberStore(cfg.subscriber_file)
    client = None
    if not args.dry_run:
        client = TelegramClient(cfg.bot_token, cfg.chat_id, timeout=cfg.timeout)
        # Welcome new /start chats and drop /stop chats before delivering.
        sync_subscribers(client, subs, cfg)
        if args.sync_only:
            if subs.dirty:
                subs.save()
                log.info("Subscribers updated: %s", cfg.subscriber_file)
            log.info("Sync complete: %d subscriber(s).", subs.count())
            return 0

    # An empty/no-op store when --no-state, so nothing is read or written.
    store = SeenStore(
        cfg.state_file if not args.no_state else "/dev/null",
        ttl_days=cfg.state_ttl_days,
    )

    articles = select_articles(cfg, store, lookback)
    if not articles:
        log.info("No new articles within the last %dh. Nothing to send.", lookback)
        if subs.dirty:
            subs.save()
        return 0

    # Generate 3 takeaways per article (best-effort — degrades to feed blurb).
    if cfg.summarize:
        summarize(articles, cfg.anthropic_api_key, cfg.summary_model,
                  timeout=max(cfg.timeout, 60))

    # One rich post per article. Caption length is the limit when a photo is
    # attached, otherwise the full message limit.
    posts = []
    for art in articles:
        use_photo = cfg.photos and bool(art.image_url)
        limit = MAX_CAPTION_LEN if use_photo else MAX_MSG_LEN
        posts.append((art, render_post(art, max_len=limit),
                      art.image_url if use_photo else None))

    log.info("Prepared %d post(s).", len(posts))

    if args.dry_run:
        for i, (art, text, photo) in enumerate(posts, 1):
            img = f"  [photo: {photo}]" if photo else "  [no photo]"
            print(f"\n===== POST {i}/{len(posts)} (score={art.score:.1f}){img} =====\n{text}")
        return 0

    # Cache this batch so /latest can replay it on demand (no refetch, no cost).
    save_last_digest(cfg.last_digest_file,
                     [(text, photo) for _, text, photo in posts])

    recipients = _recipients(cfg, subs)
    if not recipients:
        log.warning(
            "Nobody to send to: no subscribers and no TELEGRAM_CHAT_ID set. "
            "Share your bot link so people can /start to subscribe."
        )
        if subs.dirty:
            subs.save()
        return 0

    log.info("Delivering to %d recipient(s).", len(recipients))
    sent_uids = []
    for art, text, photo in posts:
        delivered = False
        for cid in list(recipients):
            try:
                client.send_post(text, photo_url=photo, chat_id=cid)
                delivered = True
            except RuntimeError as exc:
                # Drop chats that blocked the bot / no longer exist so we stop
                # retrying them; log anything else as a transient failure.
                if is_unreachable(exc) and subs.remove(cid):
                    recipients.remove(cid)
                    log.info("Dropped unreachable subscriber %s (%s)", cid, exc)
                else:
                    log.warning("Failed to send %r to %s: %s",
                                art.title[:50], cid, exc)
            time.sleep(cfg.send_delay)
        if delivered:
            sent_uids.append(art.uid)
    log.info("Sent %d/%d post(s) to %d recipient(s).",
             len(sent_uids), len(posts), len(recipients))

    if subs.dirty:
        subs.save()
        log.info("Subscribers updated: %s", cfg.subscriber_file)

    if not args.no_state and sent_uids:
        # Only mark what actually went out, so a failed send retries next run.
        store.mark(sent_uids)
        store.save()
        log.info("State updated: %s", cfg.state_file)
    return 0


if __name__ == "__main__":
    sys.exit(run())
