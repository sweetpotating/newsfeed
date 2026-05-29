"""Optional Telegram notifications for rebalance summaries and risk alerts.

No-ops silently if TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are unset, so the
engine never fails just because notifications aren't configured.
"""
from __future__ import annotations

import os

from .logging_config import get_logger

log = get_logger("notify")


def notify(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log.debug("Notifications disabled (no Telegram credentials).")
        return
    try:
        import requests

        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
        if resp.status_code != 200:
            log.warning("Telegram notify failed: %s %s", resp.status_code, resp.text[:200])
    except Exception as e:  # noqa: BLE001
        log.warning("Telegram notify error: %s", e)
