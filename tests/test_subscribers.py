import json

from ainews import digest
from ainews.classifier import classify
from ainews.config import Config
from ainews.lastdigest import load_last_digest, save_last_digest
from ainews.models import Article
from ainews.subscribe import is_unreachable, sync_subscribers
from ainews.subscribers import SubscriberStore


class FakeClient:
    """Duck-typed Telegram client for subscriber sync tests."""

    def __init__(self, updates):
        self._updates = updates
        self.sent = []   # (chat_id, text)
        self.posts = []  # (chat_id, text, photo)

    def get_updates(self, offset=0, limit=100):
        # Honour the offset like Telegram does: only return >= offset.
        return [u for u in self._updates if u["update_id"] >= offset]

    def send_message(self, text, disable_preview=True, chat_id=None):
        self.sent.append((chat_id, text))
        return {"ok": True}

    def send_post(self, text, photo_url=None, chat_id=None):
        self.posts.append((chat_id, text, photo_url))
        return {"ok": True}


def _cfg(tmp_path, **over):
    return Config(send_delay=0.0,
                  last_digest_file=str(tmp_path / "last_digest.json"), **over)


def _cmd(update_id, chat_id, text, **chat):
    return {"update_id": update_id,
            "message": {"chat": {"id": chat_id, **chat}, "text": text}}


def _start(update_id, chat_id, **chat):
    return _cmd(update_id, chat_id, "/start", **chat)


def _stop(update_id, chat_id):
    return _cmd(update_id, chat_id, "/stop")


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
    client = FakeClient([_start(10, 111, first_name="Bo"), _start(11, 222)])
    added, removed = sync_subscribers(client, store, _cfg(tmp_path))
    assert (added, removed) == (2, 0)
    assert store.has("111") and store.has("222")
    assert store.offset == 11
    # Each new subscriber got exactly one welcome message.
    assert {cid for cid, _ in client.sent} == {"111", "222"}


def test_sync_offset_skips_processed(tmp_path):
    store = SubscriberStore(str(tmp_path / "s.json"))
    store.set_offset(10)              # already processed up to update 10
    client = FakeClient([_start(10, 111), _start(11, 222)])
    added, _ = sync_subscribers(client, store, _cfg(tmp_path))
    assert added == 1                 # only update 11 is new
    assert store.has("222") and not store.has("111")


def test_sync_stop_removes(tmp_path):
    store = SubscriberStore(str(tmp_path / "s.json"))
    store.add(333)
    client = FakeClient([_stop(20, 333)])
    added, removed = sync_subscribers(client, store, _cfg(tmp_path))
    assert (added, removed) == (0, 1)
    assert not store.has("333")


def test_sync_start_when_already_subscribed(tmp_path):
    store = SubscriberStore(str(tmp_path / "s.json"))
    store.add(444)
    client = FakeClient([_start(30, 444)])
    added, _ = sync_subscribers(client, store, _cfg(tmp_path))
    assert added == 0                              # not added twice
    assert len(client.sent) == 1                   # but still got a reply


def test_latest_replays_cached_digest(tmp_path):
    cfg = _cfg(tmp_path)
    save_last_digest(cfg.last_digest_file,
                     [("Post one", "https://img/1.jpg"), ("Post two", None)])
    store = SubscriberStore(str(tmp_path / "s.json"))
    store.add(555)
    client = FakeClient([_cmd(40, 555, "/latest")])
    sync_subscribers(client, store, cfg)
    # Both cached posts were re-sent to the requester via send_post.
    assert [(c, t) for c, t, _ in client.posts] == [
        ("555", "Post one"), ("555", "Post two")]
    assert client.posts[0][2] == "https://img/1.jpg"


def test_news_alias_and_empty_cache(tmp_path):
    cfg = _cfg(tmp_path)   # no cache written
    store = SubscriberStore(str(tmp_path / "s.json"))
    client = FakeClient([_cmd(41, 666, "/news")])
    sync_subscribers(client, store, cfg)
    assert client.posts == []                       # nothing to replay
    assert len(client.sent) == 1                     # got a "no digest yet" note


def test_help_command(tmp_path):
    store = SubscriberStore(str(tmp_path / "s.json"))
    client = FakeClient([_cmd(42, 777, "/help")])
    sync_subscribers(client, store, _cfg(tmp_path))
    assert len(client.sent) == 1 and client.sent[0][0] == "777"


def test_lastdigest_roundtrip(tmp_path):
    path = str(tmp_path / "ld.json")
    save_last_digest(path, [("a", None), ("b", "http://x/y.png")])
    assert load_last_digest(path) == [("a", None), ("b", "http://x/y.png")]
    assert load_last_digest(str(tmp_path / "missing.json")) == []


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


def _run_digest_with(monkeypatch, tmp_path, env, client_factory, n_posts=2):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x:y")
    monkeypatch.setenv("AINEWS_STATE_FILE", str(tmp_path / "seen.json"))
    monkeypatch.setenv("AINEWS_SUBSCRIBER_FILE", str(tmp_path / "subs.json"))
    monkeypatch.setenv("AINEWS_LAST_DIGEST_FILE", str(tmp_path / "ld.json"))
    monkeypatch.setenv("AINEWS_SUMMARIZE", "0")
    monkeypatch.setenv("AINEWS_SEND_DELAY_MS", "0")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    arts = [classify(Article(title=f"Post {i}", link=f"https://x/{i}",
                             source="Src", summary="b")) for i in range(n_posts)]
    monkeypatch.setattr(digest, "select_articles", lambda *a, **k: arts)
    captured = {}
    monkeypatch.setattr(digest, "TelegramClient",
                        lambda *a, **k: captured.setdefault("c", client_factory()))
    assert digest.run([]) == 0
    return captured["c"], arts


def test_channel_broadcast_plus_subscribers(tmp_path, monkeypatch):
    subs = SubscriberStore(str(tmp_path / "subs.json"))
    subs.add(111)
    subs.save()
    client, arts = _run_digest_with(
        monkeypatch, tmp_path,
        {"TELEGRAM_CHANNEL_ID": "@mychan"}, lambda: FanoutClient())
    # Each post went to the channel once AND to the subscriber.
    per_post = {}
    for cid, text in client.delivered:
        per_post.setdefault(text, set()).add(cid)
    for s in per_post.values():
        assert s == {"@mychan", "111"}


def test_channel_only_no_subscribers(tmp_path, monkeypatch):
    client, arts = _run_digest_with(
        monkeypatch, tmp_path,
        {"TELEGRAM_CHANNEL_ID": "@mychan"}, lambda: FanoutClient())
    assert {cid for cid, _ in client.delivered} == {"@mychan"}
    # The batch is still cached for /latest.
    assert load_last_digest(str(tmp_path / "ld.json"))


def test_channel_failure_does_not_drop_subscribers(tmp_path, monkeypatch):
    subs = SubscriberStore(str(tmp_path / "subs.json"))
    subs.add(111)
    subs.save()
    # Channel send fails (bot not admin); subscriber must be unaffected.
    client, _ = _run_digest_with(
        monkeypatch, tmp_path,
        {"TELEGRAM_CHANNEL_ID": "@bad"}, lambda: FanoutClient(dead="@bad"))
    assert {cid for cid, _ in client.delivered} == {"111"}
    reloaded = SubscriberStore(str(tmp_path / "subs.json"))
    assert reloaded.has("111")          # channel failure never removes a sub


def test_target_channel_only_excludes_subscribers(tmp_path, monkeypatch):
    subs = SubscriberStore(str(tmp_path / "subs.json"))
    subs.add(111)
    subs.save()
    client, _ = _run_digest_with(
        monkeypatch, tmp_path,
        {"TELEGRAM_CHANNEL_ID": "@c", "AINEWS_TARGET": "channel"},
        lambda: FanoutClient())
    assert {cid for cid, _ in client.delivered} == {"@c"}   # no DM to 111


def test_target_bot_only_excludes_channel(tmp_path, monkeypatch):
    subs = SubscriberStore(str(tmp_path / "subs.json"))
    subs.add(111)
    subs.save()
    client, _ = _run_digest_with(
        monkeypatch, tmp_path,
        {"TELEGRAM_CHANNEL_ID": "@c", "AINEWS_TARGET": "bot"},
        lambda: FanoutClient())
    assert {cid for cid, _ in client.delivered} == {"111"}  # channel skipped


def test_digest_fans_out_and_drops_dead(tmp_path, monkeypatch):
    seen = tmp_path / "seen.json"
    subs_path = tmp_path / "subs.json"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x:y")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")        # owner, always included
    monkeypatch.setenv("AINEWS_STATE_FILE", str(seen))
    monkeypatch.setenv("AINEWS_SUBSCRIBER_FILE", str(subs_path))
    monkeypatch.setenv("AINEWS_LAST_DIGEST_FILE", str(tmp_path / "ld.json"))
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

    # The batch was cached for /latest replay.
    assert load_last_digest(str(tmp_path / "ld.json"))
