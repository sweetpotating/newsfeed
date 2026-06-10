"""Process incoming /start and /stop commands into the subscriber list.

The bot has no server, so instead of a webhook it long-polls Telegram's
``getUpdates`` each run. New ``/start`` chats are added (and welcomed),
``/stop`` chats are removed (and bid farewell), and the update offset is
advanced so the same message is never processed twice.
"""

from __future__ import annotations

import logging

from .subscribers import SubscriberStore
from .telegram import TelegramClient

log = logging.getLogger("ainews.subscribe")

WELCOME = (
    "👋 <b>You're subscribed to the AI News digest!</b>\n\n"
    "You'll get a curated roundup of AI-platform, agentic-commerce and "
    "industry news twice a day (08:00 &amp; 18:00 SGT), with 3 quick takeaways "
    "per story.\n\n"
    "Send /stop any time to unsubscribe."
)

GOODBYE = (
    "✅ <b>You've been unsubscribed.</b>\n"
    "No more digests will be sent. Send /start whenever you'd like them back."
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


def sync_subscribers(client: TelegramClient, store: SubscriberStore) -> tuple[int, int]:
    """Pull new updates and apply /start, /stop. Returns (added, removed)."""
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

        msg = upd.get("message") or upd.get("channel_post")
        if not isinstance(msg, dict):
            continue
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            continue
        text = (msg.get("text") or "").strip().lower()

        if text.startswith("/start"):
            if store.add(
                chat_id,
                first_name=chat.get("first_name", ""),
                username=chat.get("username", ""),
            ):
                added += 1
                try:
                    client.send_message(WELCOME, chat_id=str(chat_id))
                except RuntimeError as exc:
                    log.warning("Welcome to %s failed: %s", chat_id, exc)
        elif text.startswith("/stop"):
            if store.remove(chat_id):
                removed += 1
                try:
                    client.send_message(GOODBYE, chat_id=str(chat_id))
                except RuntimeError:
                    pass  # leaving anyway; ignore farewell failures

    if max_update_id:
        store.set_offset(max_update_id)

    if added or removed:
        log.info("Subscribers: +%d / -%d (total now %d)",
                 added, removed, store.count())
    return added, removed
