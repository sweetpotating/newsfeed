import json

from ainews import digest
from ainews.classifier import classify
from ainews.config import Config
from ainews.lastdigest import save_last_digest
from ainews.listener import COOLDOWN_MSG, serve
from ainews.models import Article
from ainews.subscribe import HELP, WELCOME, handle_update
from ainews.subscribers import SubscriberStore


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class ListenerClient:
    """Serves queued batches of updates, then idles until the deadline."""

    def __init__(self, batches, clock, step=30.0):
        self.batches = list(batches)
        self.clock = clock
        self.step = step
        self.calls = []          # (offset, poll_timeout)
        self.sent = []           # (chat_id, text)
        self.posts = []          # (chat_id, text, photo)

    def get_updates(self, offset=0, limit=100, poll_timeout=0):
        self.calls.append((offset, poll_timeout))
        self.clock.now += self.step
        batch = self.batches.pop(0) if self.batches else []
        if isinstance(batch, Exception):
            raise batch
        return [u for u in batch if u["update_id"] >= offset]

    def send_message(self, text, disable_preview=True, chat_id=None):
        self.sent.append((chat_id, text))

    def send_post(self, text, photo_url=None, chat_id=None):
        self.posts.append((chat_id, text, photo_url))


class FakeRepo:
    def __init__(self):
        self.pulls = 0
        self.commits = []

    def pull(self):
        self.pulls += 1
        return True

    def commit_and_push(self, paths, message):
        self.commits.append((tuple(paths), message))
        return True


def _msg(uid, chat_id, text, ctype="private"):
    return {"update_id": uid,
            "message": {"chat": {"id": chat_id, "type": ctype}, "text": text}}


def _cfg(tmp_path):
    return Config(send_delay=0.0,
                  subscriber_file=str(tmp_path / "subs.json"),
                  last_digest_file=str(tmp_path / "ld.json"))


def _serve(tmp_path, batches, minutes=5, repo=None):
    cfg = _cfg(tmp_path)
    clock = FakeClock()
    client = ListenerClient(batches, clock)
    store = SubscriberStore(cfg.subscriber_file)
    serve(client, store, cfg, minutes, repo=repo, clock=clock,
          sleep=lambda s: None)
    return client, store, cfg


def test_start_gets_instant_welcome_and_is_persisted(tmp_path):
    repo = FakeRepo()
    client, store, cfg = _serve(tmp_path, [[_msg(5, 111, "/start")]],
                                repo=repo)
    assert ("111", WELCOME) in client.sent
    saved = json.loads((tmp_path / "subs.json").read_text())
    assert "111" in saved["subscribers"]
    assert saved["offset"] == 5
    assert repo.commits and repo.commits[0][0] == (cfg.subscriber_file,)


def test_latest_refreshes_cache_and_is_rate_limited(tmp_path):
    save_last_digest(str(tmp_path / "ld.json"), [("Post A", None)])
    repo = FakeRepo()
    client, _, _ = _serve(tmp_path,
                          [[_msg(1, 222, "/latest"), _msg(2, 222, "/latest")]],
                          repo=repo)
    assert client.posts == [("222", "Post A", None)]    # replayed once
    assert ("222", COOLDOWN_MSG) in client.sent         # second was throttled
    assert repo.pulls == 1                              # pulled before replay


def test_block_event_removes_subscriber(tmp_path):
    cfg = _cfg(tmp_path)
    pre = SubscriberStore(cfg.subscriber_file)
    pre.add(333)
    pre.save()
    blocked = {"update_id": 9, "my_chat_member": {
        "chat": {"id": 333, "type": "private"},
        "new_chat_member": {"status": "kicked"}}}
    _, store, _ = _serve(tmp_path, [[blocked]])
    assert not store.has("333")
    saved = json.loads((tmp_path / "subs.json").read_text())
    assert "333" not in saved["subscribers"]


def test_survives_poll_errors_and_acknowledges_on_exit(tmp_path):
    client, store, _ = _serve(
        tmp_path, [RuntimeError("Conflict: terminated by other getUpdates"),
                   [_msg(7, 444, "/help")]])
    assert ("444", HELP) in client.sent       # kept going after the error
    # Final call acknowledges everything handled, without waiting.
    assert client.calls[-1] == (8, 0)


def test_stops_at_deadline(tmp_path):
    client, _, _ = _serve(tmp_path, [], minutes=2)
    # 2 minutes at 30s per poll, plus the final acknowledge (no offset yet, so
    # none is sent).
    assert len(client.calls) == 4


def test_unknown_dm_text_gets_help_but_groups_are_ignored(tmp_path):
    cfg = _cfg(tmp_path)
    store = SubscriberStore(cfg.subscriber_file)
    client = ListenerClient([], FakeClock())
    handle_update(client, store, cfg, _msg(1, 555, "hello?"))
    handle_update(client, store, cfg, _msg(2, -100, "chatter", ctype="group"))
    assert client.sent == [("555", HELP)]


class NoPollClient:
    def __init__(self, *a, **k):
        self.delivered = []

    def get_updates(self, *a, **k):
        raise AssertionError("digest must not poll when --no-sync is set")

    def send_post(self, text, photo_url=None, chat_id=None):
        if chat_id == "222":
            raise RuntimeError("Forbidden: bot was blocked by the user")
        self.delivered.append(chat_id)


def test_digest_no_sync_never_polls_or_rewrites_subscribers(tmp_path,
                                                            monkeypatch):
    subs_path = tmp_path / "subs.json"
    s = SubscriberStore(str(subs_path))
    s.add(111)
    s.add(222)
    s.save()
    before = subs_path.read_text()

    for k, v in {"TELEGRAM_BOT_TOKEN": "x:y",
                 "AINEWS_STATE_FILE": str(tmp_path / "seen.json"),
                 "AINEWS_SUBSCRIBER_FILE": str(subs_path),
                 "AINEWS_LAST_DIGEST_FILE": str(tmp_path / "ld.json"),
                 "AINEWS_SUMMARIZE": "0",
                 "AINEWS_SEND_DELAY_MS": "0"}.items():
        monkeypatch.setenv(k, v)
    arts = [classify(Article(title=f"Story {i}", link=f"https://x/{i}",
                             source="Src", summary="b")) for i in range(2)]
    monkeypatch.setattr(digest, "select_articles", lambda *a, **k: arts)
    client = NoPollClient()
    monkeypatch.setattr(digest, "TelegramClient", lambda *a, **k: client)

    assert digest.run(["--target", "bot", "--no-sync"]) == 0
    assert client.delivered == ["111", "111"]   # 222 skipped after 1st failure
    assert subs_path.read_text() == before      # listener owns this file
