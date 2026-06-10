import json

from ainews import digest
from ainews.classifier import classify
from ainews.models import Article
from ainews.subscribe import is_unreachable, sync_subscribers
from ainews.subscribers import SubscriberStore


class FakeClient:
    """Duck-typed Telegram client for subscriber sync tests."""

    def __init__(self, updates):
        self._updates = updates
        self.sent = []  # (chat_id, text)

    def get_updates(self, offset=0, limit=100):
        # Honour the offset like Telegram does: only return >= offset.
        return [u for u in self._updates if u["update_id"] >= offset]

    def send_message(self, text, disable_preview=True, chat_id=None):
        self.sent.append((chat_id, text))
        return {"ok": True}


def _start(update_id, chat_id, **chat):
    return {"update_id": update_id,
            "message": {"chat": {"id": chat_id, **chat}, "text": "/start"}}


def _stop(update_id, chat_id):
    return {"update_id": update_id,
            "message": {"chat": {"id": chat_id}, "text": "/stop"}}


def test_store_roundtrip(tmp_path):
    path = tmp_path / "subs.json"
    s = SubscriberStore(str(path))
    assert s.count() == 0
    assert s.add(111, first_name="Alice", username="alice") is True
    assert s.add(111) is False                      # no duplicate
    s.set_offset(42)
    assert s.dirty is True
    s.save()
    assert s.dirty is False

    reloaded = SubscriberStore(str(path))
    assert reloaded.has("111")
    assert reloaded.offset == 42
    assert reloaded.count() == 1
    data = json.loads(path.read_text())
    assert data["subscribers"]["111"]["first_name"] == "Alice"


def test_remove_and_dirty(tmp_path):
    s = SubscriberStore(str(tmp_path / "s.json"))
    s.add(5)
    s.save()
    assert s.dirty is False
    assert s.remove(999) is False and s.dirty is False   # nothing removed
    assert s.remove(5) is True and s.dirty is True


def test_sync_adds_and_welcomes(tmp_path):
    store = SubscriberStore(str(tmp_path / "s.json"))
    client = FakeClient([_start(10, 111, first_name="Bo"),
                         _start(11, 222)])
    added, removed = sync_subscribers(client, store)
    assert (added, removed) == (2, 0)
    assert store.has("111") and store.has("222")
    assert store.offset == 11
    # Each new subscriber got exactly one welcome message.
    assert {cid for cid, _ in client.sent} == {"111", "222"}


def test_sync_offset_skips_processed(tmp_path):
    store = SubscriberStore(str(tmp_path / "s.json"))
    store.set_offset(10)              # already processed up to update 10
    client = FakeClient([_start(10, 111), _start(11, 222)])
    added, _ = sync_subscribers(client, store)
    assert added == 1                 # only update 11 is new
    assert store.has("222") and not store.has("111")


def test_sync_stop_removes(tmp_path):
    store = SubscriberStore(str(tmp_path / "s.json"))
    store.add(333)
    client = FakeClient([_stop(20, 333)])
    added, removed = sync_subscribers(client, store)
    assert (added, removed) == (0, 1)
    assert not store.has("333")


def test_is_unreachable():
    assert is_unreachable("Forbidden: bot was blocked by the user")
    assert is_unreachable(RuntimeError("Bad Request: chat not found"))
    assert not is_unreachable("Too Many Requests: retry later")


class FanoutClient:
    """Records deliveries; raises 'blocked' for a designated dead chat."""

    def __init__(self, *a, dead=None, **k):
        self.dead = dead
        self.delivered = []  # (chat_id, text)

    def get_updates(self, offset=0, limit=100):
        return []

    def send_post(self, text, photo_url=None, chat_id=None):
        if chat_id == self.dead:
            raise RuntimeError("Forbidden: bot was blocked by the user")
        self.delivered.append((chat_id, text))
        return {"ok": True}


def test_digest_fans_out_and_drops_dead(tmp_path, monkeypatch):
    seen = tmp_path / "seen.json"
    subs_path = tmp_path / "subs.json"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x:y")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")        # owner, always included
    monkeypatch.setenv("AINEWS_STATE_FILE", str(seen))
    monkeypatch.setenv("AINEWS_SUBSCRIBER_FILE", str(subs_path))
    monkeypatch.setenv("AINEWS_SUMMARIZE", "0")
    monkeypatch.setenv("AINEWS_SEND_DELAY_MS", "0")

    # Two subscribers: 111 is reachable, 222 has blocked the bot.
    s = SubscriberStore(str(subs_path))
    s.add(111)
    s.add(222)
    s.save()

    art = classify(Article(title="Claude Opus ships", link="https://x.com/a",
                            source="Anthropic", summary="A blurb."))
    monkeypatch.setattr(digest, "select_articles", lambda *a, **k: [art])
    captured = {}
    monkeypatch.setattr(
        digest, "TelegramClient",
        lambda *a, **k: captured.setdefault("client", FanoutClient(dead="222")),
    )

    rc = digest.run(["--verbose"])
    assert rc == 0

    client = captured["client"]
    targets = {cid for cid, _ in client.delivered}
    assert targets == {"111", "999"}                    # 222 failed, owner kept

    # 222 was dropped from the subscriber list and persisted.
    reloaded = SubscriberStore(str(subs_path))
    assert reloaded.has("111") and not reloaded.has("222")

    # The article was marked seen (it reached at least one recipient).
    ids = json.loads(seen.read_text())["ids"]
    assert art.uid in ids
