"""Send one-off announcements (e.g. "what's new") to every reader, once.

Each file in ``announcements/`` is a Telegram HTML message. Any file not yet
listed in ``state/announced.json`` is sent to all bot subscribers, the owner
chat (TELEGRAM_CHAT_ID) and the channel (TELEGRAM_CHANNEL_ID), then recorded so
re-running never sends it twice. The GitHub workflow runs this whenever a new
announcement file is pushed.

Run:
    python -m ainews.announce
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional

from .config import Config
from .subscribers import SubscriberStore
from .telegram import TelegramClient

log = logging.getLogger("ainews.announce")

ANNOUNCE_DIR = "announcements"
SENT_FILE = "state/announced.json"


def _load_sent(path: str) -> Dict[str, int]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {str(k): int(v) for k, v in data.items()}
    except (OSError, ValueError, AttributeError):
        return {}


def _save_sent(path: str, sent: Dict[str, int]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(sent, fh, indent=1, sort_keys=True)


def recipients(cfg: Config, subs: SubscriberStore) -> List[str]:
    """Every subscriber, then the owner chat and channel, without repeats."""
    out: List[str] = []
    for cid in [*subs.chat_ids(), cfg.chat_id, cfg.channel_id]:
        if cid and cid not in out:
            out.append(cid)
    return out


def send_pending(client: TelegramClient, cfg: Config,
                 announce_dir: str = ANNOUNCE_DIR,
                 sent_file: str = SENT_FILE) -> List[str]:
    """Send every unsent announcement. Returns the names that were sent."""
    if not os.path.isdir(announce_dir):
        return []
    sent = _load_sent(sent_file)
    pending = sorted(n for n in os.listdir(announce_dir)
                     if n.endswith(".html") and n not in sent)
    if not pending:
        log.info("No new announcements.")
        return []

    targets = recipients(cfg, SubscriberStore(cfg.subscriber_file))
    for name in pending:
        with open(os.path.join(announce_dir, name), "r", encoding="utf-8") as fh:
            text = fh.read().strip()
        delivered = 0
        for cid in targets:
            try:
                client.send_message(text, chat_id=cid)
                delivered += 1
            except Exception as exc:
                log.warning("Announcement %s to %s failed: %s", name, cid, exc)
            time.sleep(cfg.send_delay)
        log.info("Sent announcement %s to %d/%d recipient(s).",
                 name, delivered, len(targets))
        # Record it even after partial failures: resending would duplicate
        # the message for everyone who already got it.
        sent[name] = int(time.time())
        _save_sent(sent_file, sent)
    return pending


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ainews.announce",
        description="Send new announcements to all readers, once.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = Config.from_env()
    cfg.require_telegram()
    client = TelegramClient(cfg.bot_token, timeout=cfg.timeout)
    send_pending(client, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
