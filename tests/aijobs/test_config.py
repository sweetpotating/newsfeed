"""Config env-var resolution, with focus on the dedicated-channel routing."""

import pytest

from aijobs.config import Config

# Env vars this module touches; cleared before each test for isolation.
_VARS = [
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "AIJOBS_BOT_TOKEN", "AIJOBS_CHAT_ID",
    "ANTHROPIC_API_KEY", "AIJOBS_SUMMARIZE",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for v in _VARS:
        monkeypatch.delenv(v, raising=False)


def test_chat_id_prefers_dedicated_channel(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "shared")
    monkeypatch.setenv("AIJOBS_CHAT_ID", "@jobs_channel")
    cfg = Config.from_env()
    assert cfg.chat_id == "@jobs_channel"


def test_chat_id_falls_back_to_shared(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "shared")
    cfg = Config.from_env()
    assert cfg.chat_id == "shared"


def test_bot_token_prefers_dedicated(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "shared-token")
    monkeypatch.setenv("AIJOBS_BOT_TOKEN", "jobs-token")
    cfg = Config.from_env()
    assert cfg.bot_token == "jobs-token"


def test_bot_token_falls_back_to_shared(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "shared-token")
    cfg = Config.from_env()
    assert cfg.bot_token == "shared-token"


def test_require_telegram_passes_with_dedicated_only(monkeypatch):
    monkeypatch.setenv("AIJOBS_BOT_TOKEN", "t")
    monkeypatch.setenv("AIJOBS_CHAT_ID", "@c")
    Config.from_env().require_telegram()  # must not raise


def test_require_telegram_reports_missing(monkeypatch):
    cfg = Config.from_env()  # nothing set
    with pytest.raises(RuntimeError) as exc:
        cfg.require_telegram()
    msg = str(exc.value)
    assert "AIJOBS_CHAT_ID" in msg
    assert "AIJOBS_BOT_TOKEN" in msg
