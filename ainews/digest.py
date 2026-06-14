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
import os
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
from .cluster import cluster_duplicates
from .similar import first_similar_index, is_similar_to_any, title_tokens
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

    # Rank everything, then de-duplicate in two passes:
    #   1) lexical — skip headlines that overlap a story shared in the last 24h
    #      or a higher-ranked pick this run (cheap, always on);
    #   2) semantic — Claude groups same-story items that are worded too
    #      differently for word overlap to catch (optional, graceful).
    # Dropped duplicates lend their outlet name to the kept story ("also
    # covered by …") and are marked seen so they don't resurface next run.
    ranked = rank(fresh, len(fresh))
    recent_tokens = store.recent_title_tokens()
    pool: List[Article] = []
    pool_tokens: List = []
    dropped_uids: List[str] = []
    # Consider a few times the final count so the semantic pass has room to work.
    pool_cap = max(cfg.max_items * 3, 15)

    for art in ranked:
        toks = title_tokens(art.title)
        if is_similar_to_any(toks, recent_tokens):
            dropped_uids.append(art.uid)            # already shared recently
            continue
        dup_idx = first_similar_index(toks, pool_tokens)
        if dup_idx is not None:
            pool[dup_idx].also_in.append(art.source)
            dropped_uids.append(art.uid)
            continue
        pool.append(art)
        pool_tokens.append(toks)
        if len(pool) >= pool_cap:
            break

    if cfg.anthropic_api_key and len(pool) > 1:
        rep_of, stale = cluster_duplicates(
            pool, store.recent_titles(), cfg.anthropic_api_key,
            cfg.summary_model, timeout=max(cfg.timeout, 60))
        survivors: List[Article] = []
        kept: dict = {}                              # pool index -> kept Article
        for i, art in enumerate(pool):
            if i in stale:
                dropped_uids.append(art.uid)
                continue
            root = _resolve_rep(i, rep_of)
            if root != i:
                rep = kept.get(root)
                if rep is not None:                  # fold into the kept story
                    rep.also_in.append(art.source)
                    rep.also_in.extend(art.also_in)  # carry its outlets over
                dropped_uids.append(art.uid)
                continue
            survivors.append(art)
            kept[i] = art
        pool = survivors

    picked = pool[: cfg.max_items]
    dropped = len(dropped_uids)
    if dropped:
        log.info("De-duplicated %d stor%s before sending.",
                 dropped, "y" if dropped == 1 else "ies")
        store.mark(dropped_uids)        # don't reconsider these duplicates
    return picked


def _resolve_rep(i: int, rep_of: dict) -> int:
    """Follow the representative chain to the cluster's root index."""
    seen = set()
    while i in rep_of and i not in seen:
        seen.add(i)
        i = rep_of[i]
    return i


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
    parser.add_argument("--target", choices=["all", "bot", "channel"],
                        default=None,
                        help="Where to deliver: 'bot' = DM subscribers (+owner "
                             "chat), 'channel' = the broadcast channel, 'all' = "
                             "both. Defaults to AINEWS_TARGET or 'all'.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    target = (args.target or os.environ.get("AINEWS_TARGET") or "all").lower()
    use_bot = target in ("all", "bot")
    use_channel = target in ("all", "channel")

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
        # Subscriber processing is a bot concern; skip it for channel-only runs.
        if use_bot or args.sync_only:
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
    # /latest is a bot feature, so only bot-facing runs refresh the cache.
    if use_bot:
        save_last_digest(cfg.last_digest_file,
                         [(text, photo) for _, text, photo in posts])

    # A channel is a single broadcast target that reaches all its members with
    # one send (so it scales without a per-member loop). DM recipients are the
    # subscriber list plus the optional owner chat. The --target flag selects
    # which of these this run delivers to.
    channel = cfg.channel_id if use_channel else ""
    dm_recipients = _recipients(cfg, subs) if use_bot else []
    if not channel and not dm_recipients:
        log.warning(
            "Nobody to send to: no channel, no subscribers and no "
            "TELEGRAM_CHAT_ID set. Set TELEGRAM_CHANNEL_ID to broadcast to a "
            "channel, or share your bot link so people can /start to subscribe."
        )
        if subs.dirty:
            subs.save()
        return 0

    log.info("Delivering %d post(s) to %s%d DM recipient(s).", len(posts),
             "channel + " if channel else "", len(dm_recipients))
    sent_uids = []
    sent_titles = []
    for art, text, photo in posts:
        delivered = False
        # Broadcast to the channel once; reaches every member.
        if channel:
            try:
                client.send_post(text, photo_url=photo, chat_id=channel)
                delivered = True
            except RuntimeError as exc:
                log.warning("Channel post to %s failed (is the bot an admin "
                            "with post rights?): %s", channel, exc)
            time.sleep(cfg.send_delay)
        # Fan out to DM subscribers (and the owner chat).
        for cid in list(dm_recipients):
            try:
                client.send_post(text, photo_url=photo, chat_id=cid)
                delivered = True
            except RuntimeError as exc:
                # Drop chats that blocked the bot / no longer exist so we stop
                # retrying them; log anything else as a transient failure.
                if is_unreachable(exc) and subs.remove(cid):
                    dm_recipients.remove(cid)
                    log.info("Dropped unreachable subscriber %s (%s)", cid, exc)
                else:
                    log.warning("Failed to send %r to %s: %s",
                                art.title[:50], cid, exc)
            time.sleep(cfg.send_delay)
        if delivered:
            sent_uids.append(art.uid)
            sent_titles.append(art.title)
    log.info("Sent %d/%d post(s)%s to %d DM recipient(s).",
             len(sent_uids), len(posts),
             " to channel" if channel else "", len(dm_recipients))

    if subs.dirty:
        subs.save()
        log.info("Subscribers updated: %s", cfg.subscriber_file)

    if not args.no_state and sent_uids:
        # Only mark what actually went out, so a failed send retries next run.
        # Titles feed the 24h near-duplicate filter for future runs.
        store.mark(sent_uids)
        store.mark_titles(sent_titles)
        store.save()
        log.info("State updated: %s", cfg.state_file)
    return 0


if __name__ == "__main__":
    sys.exit(run())
