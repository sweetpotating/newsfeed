"""Minimal Telegram Bot API client for Mimi Helen Bot.

Talks to the HTTP API directly via ``requests`` — no heavyweight framework. On
top of the basic ``sendMessage`` it supports inline keyboards (the ✅ / ⏰
buttons), answering callback queries, editing messages, and long-polling
``getUpdates`` for the interactive ``serve`` mode. Handles HTML parse mode,
429 rate limiting and basic retries.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger("mimihelen.telegram")

API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramClient:
    def __init__(self, token: str, chat_id: str = "", timeout: int = 20):
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout

    def _post(self, method: str, payload: dict, timeout: Optional[int] = None) -> dict:
        url = API_BASE.format(token=self.token, method=method)
        for attempt in range(5):
            resp = requests.post(url, json=payload, timeout=timeout or self.timeout)
            if resp.status_code == 429:
                retry_after = 1
                try:
                    retry_after = int(
                        resp.json().get("parameters", {}).get("retry_after", 1)
                    )
                except (ValueError, KeyError, AttributeError):
                    pass
                log.warning("Rate limited; sleeping %ss", retry_after)
                time.sleep(retry_after + 1)
                continue
            if resp.status_code >= 500:
                wait = 2 ** attempt
                log.warning("Telegram %s; retrying in %ss", resp.status_code, wait)
                time.sleep(wait)
                continue
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(
                    f"Telegram API error: {data.get('description', resp.text)}"
                )
            return data
        raise RuntimeError(f"Telegram {method} failed after retries")

    def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        reply_markup: Optional[dict] = None,
        disable_preview: bool = True,
    ) -> dict:
        payload: Dict[str, Any] = {
            "chat_id": chat_id or self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_preview,
            "disable_notification": False,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return self._post("sendMessage", payload)

    def edit_message_text(
        self, chat_id: str, message_id: int, text: str,
        reply_markup: Optional[dict] = None,
    ) -> dict:
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return self._post("editMessageText", payload)

    def answer_callback_query(self, callback_id: str, text: str = "") -> dict:
        payload: Dict[str, Any] = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text
        return self._post("answerCallbackQuery", payload)

    def set_my_commands(self, commands: List[Dict[str, str]]) -> dict:
        return self._post("setMyCommands", {"commands": commands})

    def get_updates(self, offset: Optional[int], poll_timeout: int) -> List[dict]:
        # Long-poll: keep the HTTP request open up to poll_timeout seconds.
        payload: Dict[str, Any] = {
            "timeout": poll_timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        data = self._post("getUpdates", payload, timeout=poll_timeout + 10)
        return data.get("result", [])


def reminder_keyboard() -> dict:
    """The action buttons attached to each reminder."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Done", "callback_data": "done"},
                {"text": "⏰ Snooze 15m", "callback_data": "snooze"},
            ],
            [
                {"text": "📊 Today", "callback_data": "today"},
                {"text": "💡 Tip", "callback_data": "tip"},
            ],
        ]
    }
