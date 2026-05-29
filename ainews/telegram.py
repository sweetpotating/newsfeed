"""Minimal Telegram Bot API client (sendMessage only).

Uses the HTTP API directly via ``requests`` — no heavyweight bot framework is
needed for a push-only digest. Handles HTML parse mode, 429 rate limiting and
basic retries.
"""

from __future__ import annotations

import logging
import time
from typing import List

import requests

log = logging.getLogger("ainews.telegram")

API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramClient:
    def __init__(self, token: str, chat_id: str, timeout: int = 20):
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout

    def _post(self, method: str, payload: dict) -> dict:
        url = API_BASE.format(token=self.token, method=method)
        for attempt in range(5):
            resp = requests.post(url, json=payload, timeout=self.timeout)
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
        raise RuntimeError("Telegram send failed after retries")

    def send_message(self, text: str, disable_preview: bool = True) -> dict:
        return self._post(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": disable_preview,
                "disable_notification": False,
            },
        )

    def send_all(self, messages: List[str]) -> int:
        sent = 0
        for msg in messages:
            if not msg.strip():
                continue
            self.send_message(msg)
            sent += 1
            time.sleep(0.6)  # stay well under Telegram's ~1 msg/sec to a chat
        return sent
