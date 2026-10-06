"""Process incoming bot commands into the subscriber list and on-demand sends.

The bot has no server, so instead of a webhook it polls Telegram's
``getUpdates`` — continuously in the always-on listener (``ainews.listener``),
or once per run with ``--sync-only`` — and handles a small set of commands:

* ``/start``  — subscribe (and get a welcome explaining what to expect)
* ``/stop``   — unsubscribe
* ``/latest`` (alias ``/news``) — re-send the most recent digest to the asker
* ``/help``   — list the commands

The update offset is advanced so the same message is never processed twice.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional, Tuple

from .config import Config
from .lastdigest import load_last_digest
from .subscribers import SubscriberStore
from .telegram import TelegramClient

log = logging.getLogger("ainews.subscribe")

WELCOME = (
    "👋 <b>Welcome to the AI News digest!</b>\n\n"
    "I send a curated roundup of the latest <b>AI</b> news — AI platforms "
    "(Claude, ChatGPT, Gemini, …), agentic payments &amp; commerce, and the "
    "wider AI industry — each with <b>3 quick takeaways</b> and a link to read "
    "more.\n\n"
    "🗓 <b>When:</b> twice a day, 08:00 &amp; 18:00 (Singapore time).\n\n"
    "<b>Commands</b>\n"
    "• /latest — send me the most recent digest now\n"
    "• /help — what I can do\n"
    "• /stop — unsubscribe\n\n"
    "You're all set ✅ — your next digest arrives at the scheduled time. "
    "Send /latest to see one right away."
)

ALREADY_SUBSCRIBED = (
    "✅ You're already subscribed. Send /latest to see the most recent digest, "
    "or /help for all commands."
)

GOODBYE = (
    "✅ <b>You've been unsubscribed.</b>\n"
    "No more digests will be sent. Send /start whenever you'd like them back."
)

HELP = (
    "🤖 <b>AI News digest — commands</b>\n"
    "• /latest — send the most recent digest now\n"
    "• /start — subscribe (digests twice a day)\n"
    "• /stop — unsubscribe\n"
    "• /help — show this message\n\n"
    "Digests arrive at 08:00 &amp; 18:00 Singapore time."
)

NO_DIGEST_YET = (
    "📭 No digest has been generated yet. Your first one will arrive at the "
    "next scheduled time (08:00 / 18:00 SGT) — hang tight!"
)

# Telegram errors that mean the chat is permanently unreachable.
_DEAD_CHAT_MARKERS = (
    "bot was blocked",
    "chat not found",
    "user is deactivated",
    "deactivated",
    "forbidden",
    "bot can't initiate",
)


def is_unreachable(error: object) -> bool:
    """True if a send error means the subscriber should be dropped."""
    msg = str(error).lower()
    return any(marker in msg for marker in _DEAD_CHAT_MARKERS)


def _safe_send(client: TelegramClient, text: str, chat_id: str) -> None:
    try:
        client.send_message(text, chat_id=chat_id)
    except RuntimeError as exc:
        log.warning("Send to %s failed: %s", chat_id, exc)


def send_latest(client: TelegramClient, cfg: Config, chat_id: str) -> bool:
    """Replay the most recent digest to one chat. Returns True if sent."""
    posts = load_last_digest(cfg.last_digest_file)
    if not posts:
        _safe_send(client, NO_DIGEST_YET, chat_id)
        return False
    for text, photo in posts:
        try:
            client.send_post(text, photo_url=photo, chat_id=chat_id)
        except RuntimeError as exc:
            log.warning("Replay to %s failed: %s", chat_id, exc)
        time.sleep(cfg.send_delay)
    log.info("Replayed %d post(s) to %s on request.", len(posts), chat_id)
    return True


def handle_update(client: TelegramClient, store: SubscriberStore, cfg: Config,
                  upd: dict,
                  on_latest: Optional[Callable[[str], None]] = None
                  ) -> Tuple[int, int]:
    """Apply one Telegram update. Returns (added, removed) subscriber counts.

    ``on_latest`` replaces the default /latest handling (the always-on
    listener uses it to refresh the digest cache and rate-limit replays).
    """
    member = upd.get("my_chat_member")
    if isinstance(member, dict):
        # The user blocked the bot (or left): stop sending to them.
        status = (member.get("new_chat_member") or {}).get("status")
        cid = str((member.get("chat") or {}).get("id", ""))
        if cid and status in ("kicked", "left") and store.remove(cid):
            log.info("Subscriber %s blocked the bot; removed.", cid)
            return 0, 1
        return 0, 0

    msg = upd.get("message") or upd.get("channel_post")
    if not isinstance(msg, dict):
        return 0, 0
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return 0, 0
    cid = str(chat_id)
    text = (msg.get("text") or "").strip().lower()

    if text.startswith("/start"):
        if store.add(cid, first_name=chat.get("first_name", ""),
                     username=chat.get("username", "")):
            _safe_send(client, WELCOME, cid)
            return 1, 0
        _safe_send(client, ALREADY_SUBSCRIBED, cid)
    elif text.startswith("/stop"):
        if store.remove(cid):
            _safe_send(client, GOODBYE, cid)
            return 0, 1
    elif text.startswith("/latest") or text.startswith("/news"):
        if on_latest is not None:
            on_latest(cid)
        else:
            send_latest(client, cfg, cid)
    elif text.startswith("/help"):
        _safe_send(client, HELP, cid)
    elif text and chat.get("type") == "private":
        # Anything else in a DM gets the command list rather than silence.
        _safe_send(client, HELP, cid)
    return 0, 0


def sync_subscribers(client: TelegramClient, store: SubscriberStore,
                     cfg: Config) -> tuple[int, int]:
    """Pull pending updates once and handle them. Returns (added, removed)."""
    fetch_offset = store.offset + 1 if store.offset else 0
    try:
        updates = client.get_updates(offset=fetch_offset)
    except RuntimeError as exc:
        log.warning("getUpdates failed: %s", exc)
        return 0, 0

    added = removed = 0
    max_update_id = store.offset
    for upd in updates:
        update_id = int(upd.get("update_id", 0))
        if update_id > max_update_id:
            max_update_id = update_id
        a, r = handle_update(client, store, cfg, upd)
        added += a
        removed += r

    if max_update_id:
        store.set_offset(max_update_id)

    if added or removed:
        log.info("Subscribers: +%d / -%d (total now %d)",
                 added, removed, store.count())
    return added, removed
