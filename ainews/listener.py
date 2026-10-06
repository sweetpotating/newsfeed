"""Always-on Telegram listener: answers bot commands within seconds.

The digest workflows run on a schedule, but people expect a bot to reply the
moment they press Start. This module long-polls Telegram's ``getUpdates`` for a
fixed time (a GitHub Actions job can run for at most 6 hours) and handles every
command as it arrives — /start, /stop, /latest, /help — using the same logic as
the one-shot ``--sync-only`` mode. It is the only process that reads updates or
writes the subscriber list; Telegram rejects two concurrent pollers.

With ``--git-sync`` (used in GitHub Actions) it also keeps the checkout current:
it pulls before replaying /latest, so the reply is the newest digest rather
than whatever was current when the listener started, and it commits + pushes
subscriber-list changes so the digest workflows see new subscribers.

Run:
    python -m ainews.listener --minutes 330 --git-sync --branch <branch>
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from typing import Callable, Dict, List, Optional

from .config import Config
from .subscribe import _safe_send, handle_update, send_latest
from .subscribers import SubscriberStore
from .telegram import TelegramClient

log = logging.getLogger("ainews.listener")

# One /latest replay sends up to ~10 posts; don't let a chat trigger it in a
# tight loop.
LATEST_COOLDOWN_SECONDS = 60
COOLDOWN_MSG = ("⏳ You just got the latest digest — "
                "send /latest again in a minute.")
SUBSCRIBERS_COMMIT_MSG = "chore: update AI news subscriber list"


class RepoSync:
    """Pulls the newest digest cache and pushes subscriber-list changes."""

    def __init__(self, branch: str):
        self.branch = branch

    def _git(self, *args: str) -> bool:
        try:
            res = subprocess.run(["git", *args], capture_output=True,
                                 text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.warning("git %s failed: %s", args[0], exc)
            return False
        if res.returncode != 0:
            log.warning("git %s failed: %s", args[0],
                        (res.stderr or res.stdout).strip()[:300])
            return False
        return True

    def pull(self) -> bool:
        return self._git("pull", "-q", "--rebase", "--autostash",
                         "origin", self.branch)

    def commit_and_push(self, paths: List[str], message: str) -> bool:
        if not self._git("add", *paths):
            return False
        # Exit status 0 means nothing is staged.
        if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
            return True
        if not self._git("commit", "-q", "-m", message):
            return False
        for attempt in range(4):
            if self._git("push", "-q", "origin", f"HEAD:{self.branch}"):
                return True
            time.sleep(2 ** attempt)
            self.pull()
        return False


def serve(client: TelegramClient, store: SubscriberStore, cfg: Config,
          minutes: float, repo: Optional[RepoSync] = None,
          poll_timeout: int = 50,
          clock: Callable[[], float] = time.monotonic,
          sleep: Callable[[float], None] = time.sleep) -> None:
    """Handle bot updates until ``minutes`` have elapsed."""
    deadline = clock() + minutes * 60
    last_latest: Dict[str, float] = {}

    def on_latest(cid: str) -> None:
        now = clock()
        if now - last_latest.get(cid, float("-inf")) < LATEST_COOLDOWN_SECONDS:
            _safe_send(client, COOLDOWN_MSG, cid)
            return
        last_latest[cid] = now
        if repo is not None:
            repo.pull()          # the digest cache may have changed since start
        send_latest(client, cfg, cid)

    def persist() -> None:
        store.save()
        if repo is not None:
            repo.commit_and_push([cfg.subscriber_file], SUBSCRIBERS_COMMIT_MSG)

    log.info("Listening for bot commands for %.0f minute(s); %d subscriber(s).",
             minutes, store.count())
    while clock() < deadline:
        wait = int(max(1, min(poll_timeout, deadline - clock())))
        try:
            updates = client.get_updates(
                offset=store.offset + 1 if store.offset else 0,
                poll_timeout=wait)
        except Exception as exc:  # network blips, 409 conflicts, bad JSON
            log.warning("getUpdates failed (%s); retrying shortly.", exc)
            sleep(5)
            continue

        changed = False
        for upd in updates:
            try:
                added, removed = handle_update(client, store, cfg, upd,
                                               on_latest=on_latest)
                changed = changed or bool(added or removed)
            except Exception as exc:
                # Never let one bad update stall the queue: log and move on.
                log.warning("Failed to handle update %s: %s",
                            upd.get("update_id"), exc)
            store.set_offset(max(store.offset, int(upd.get("update_id", 0))))

        if changed:
            log.info("Subscriber list changed; now %d subscriber(s).",
                     store.count())
            persist()

    # Acknowledge everything handled so the next listener starts clean, then
    # save the final offset.
    if store.offset:
        try:
            client.get_updates(offset=store.offset + 1, poll_timeout=0)
        except Exception as exc:
            log.warning("Final acknowledge failed: %s", exc)
    if store.dirty:
        persist()
    log.info("Listener done; %d subscriber(s).", store.count())


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ainews.listener",
        description="Answer Telegram bot commands continuously.")
    parser.add_argument("--minutes", type=float, default=330,
                        help="How long to listen before exiting (default 330).")
    parser.add_argument("--git-sync", action="store_true",
                        help="Pull before /latest and push subscriber changes "
                             "(for GitHub Actions).")
    parser.add_argument("--branch", default=os.environ.get("GITHUB_REF_NAME", ""),
                        help="Branch to pull from and push to with --git-sync.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.git_sync and not args.branch:
        parser.error("--git-sync needs --branch (or GITHUB_REF_NAME)")

    cfg = Config.from_env()
    cfg.require_telegram()
    client = TelegramClient(cfg.bot_token, timeout=cfg.timeout)
    store = SubscriberStore(cfg.subscriber_file)
    repo = RepoSync(args.branch) if args.git_sync else None
    serve(client, store, cfg, args.minutes, repo=repo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
