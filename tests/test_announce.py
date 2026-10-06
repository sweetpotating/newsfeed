import json

from ainews.announce import send_pending
from ainews.config import Config
from ainews.subscribers import SubscriberStore


class Client:
    def __init__(self, fail_for=()):
        self.sent = []
        self.fail_for = set(fail_for)

    def send_message(self, text, disable_preview=True, chat_id=None):
        if chat_id in self.fail_for:
            raise RuntimeError("Forbidden: bot was blocked by the user")
        self.sent.append((chat_id, text))


def _setup(tmp_path, subscribers=("111", "222"), chat_id="999",
           channel_id="-100"):
    subs = SubscriberStore(str(tmp_path / "subs.json"))
    for s in subscribers:
        subs.add(s)
    subs.save()
    cfg = Config(send_delay=0.0, subscriber_file=str(tmp_path / "subs.json"),
                 chat_id=chat_id, channel_id=channel_id)
    ann = tmp_path / "announcements"
    ann.mkdir()
    return cfg, ann, str(tmp_path / "announced.json")


def test_sends_to_everyone_once(tmp_path):
    cfg, ann, sent_file = _setup(tmp_path, subscribers=("111", "999"))
    (ann / "2026-10-06-whats-new.html").write_text("<b>New!</b>\n")
    client = Client()
    assert send_pending(client, cfg, str(ann), sent_file) == [
        "2026-10-06-whats-new.html"]
    # Subscribers, then owner chat (already a subscriber, so not repeated),
    # then the channel.
    assert client.sent == [("111", "<b>New!</b>"), ("999", "<b>New!</b>"),
                           ("-100", "<b>New!</b>")]
    assert "2026-10-06-whats-new.html" in json.loads(open(sent_file).read())

    # A second run (e.g. a workflow re-run) sends nothing.
    again = Client()
    assert send_pending(again, cfg, str(ann), sent_file) == []
    assert again.sent == []


def test_only_new_files_are_sent(tmp_path):
    cfg, ann, sent_file = _setup(tmp_path, channel_id="")
    (ann / "a.html").write_text("old")
    send_pending(Client(), cfg, str(ann), sent_file)
    (ann / "b.html").write_text("new")
    (ann / "notes.txt").write_text("ignored")
    client = Client()
    assert send_pending(client, cfg, str(ann), sent_file) == ["b.html"]
    assert {t for _, t in client.sent} == {"new"}


def test_one_failed_recipient_does_not_stop_the_rest(tmp_path):
    cfg, ann, sent_file = _setup(tmp_path)
    (ann / "x.html").write_text("hi")
    client = Client(fail_for={"111"})
    send_pending(client, cfg, str(ann), sent_file)
    assert [c for c, _ in client.sent] == ["222", "999", "-100"]
    # Recorded anyway, so nobody gets a duplicate on re-run.
    assert "x.html" in json.loads(open(sent_file).read())
