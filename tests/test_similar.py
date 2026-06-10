from datetime import datetime, timedelta, timezone

from ainews import digest
from ainews.config import Config
from ainews.models import Article
from ainews.similar import is_similar, title_tokens
from ainews.state import SeenStore


def _now():
    return datetime.now(timezone.utc)


def test_title_tokens_normalises():
    toks = title_tokens("Google's Gemini 3.5 Live-Translate: what's new?")
    assert "google" in toks and "gemini" in toks and "translate" in toks
    assert "s" not in toks            # single letters dropped
    assert "what" not in toks         # stopword dropped


def test_real_world_duplicate_pair_matches():
    # This pair was actually sent twice by the 2026-06-10 channel run.
    a = title_tokens("Google announces Gemini 3.5 Live Translate for "
                     "instant voice-to-voice translation")
    b = title_tokens("Google's Gemini 3.5 Live Translate delivers real-time "
                     "voice translation across 70+ languages")
    assert is_similar(a, b)


def test_distinct_stories_do_not_match():
    a = title_tokens("Anthropic launches Claude Fable 5")
    b = title_tokens("Meta signs first AI data center deal in India "
                     "with Reliance")
    assert not is_similar(a, b)
    # Same company, different stories should still pass.
    c = title_tokens("Anthropic adds prompt caching to the API")
    assert not is_similar(a, c)


def test_store_titles_roundtrip_and_window(tmp_path):
    path = str(tmp_path / "seen.json")
    s = SeenStore(path)
    s.mark_titles(["Google announces Gemini Live Translate"])
    s.save()

    reloaded = SeenStore(path)
    recent = reloaded.recent_title_tokens()
    assert len(recent) == 1
    assert is_similar(title_tokens("Google's Gemini Live Translate delivers "
                                   "real-time translation"), recent[0])
    # Outside the 24h matching window the title no longer blocks.
    assert reloaded.recent_title_tokens(window_seconds=0) == []


def _art(title, link, hours_ago=1):
    return Article(title=title, link=link, source="Src", uid=link,
                   published=_now() - timedelta(hours=hours_ago))


def test_select_skips_recent_and_in_batch_duplicates(tmp_path, monkeypatch):
    store = SeenStore(str(tmp_path / "seen.json"))
    # Shared a few hours ago: blocks similar stories for 24h.
    store.mark_titles(["Google announces Gemini Live Translate for instant "
                       "voice translation"])

    feed = [
        # Near-dup of the recently shared story -> skipped.
        _art("Google's Gemini Live Translate delivers real-time voice "
             "translation", "https://x/1"),
        # Two outlets, same new story -> only the higher-ranked one kept.
        _art("Meta signs first AI data center deal in India with Reliance",
             "https://x/2"),
        _art("Meta inks India AI data center deal with Reliance",
             "https://x/3"),
        # Distinct stories -> kept.
        _art("Apple delays AI-powered Siri in EU and China", "https://x/4"),
        _art("UWORLD humanoid companion robot secures 3,000 orders",
             "https://x/5"),
    ]
    monkeypatch.setattr(digest, "fetch_all", lambda *a, **k: list(feed))

    cfg = Config(max_items=5)
    picked = digest.select_articles(cfg, store, lookback_hours=24)
    titles = [a.title for a in picked]

    assert len(picked) == 3
    assert not any("Translate" in t for t in titles)      # 24h block
    assert sum("Reliance" in t for t in titles) == 1      # in-batch dedup
    assert any("Siri" in t for t in titles)
    assert any("robot" in t for t in titles)


DISTINCT_TITLES = [
    "Anthropic launches Claude Fable 5 with mythos safeguards",
    "Meta signs first AI data center deal in India with Reliance",
    "Apple delays AI-powered Siri in EU and China over rules",
    "UWORLD humanoid companion robot secures thousands of orders",
    "Visa expands Intelligent Commerce pilots across Asia",
    "Hugging Face benchmarks frontier ASR on code-switched speech",
    "Stripe agent toolkit adds usage-based billing primitives",
    "DeepSeek quietly updates its reasoning model weights",
]


def test_select_respects_max_items_after_dedup(tmp_path, monkeypatch):
    store = SeenStore(str(tmp_path / "seen.json"))
    feed = [_art(t, f"https://x/{i}") for i, t in enumerate(DISTINCT_TITLES)]
    monkeypatch.setattr(digest, "fetch_all", lambda *a, **k: list(feed))
    picked = digest.select_articles(Config(max_items=5), store,
                                    lookback_hours=24)
    assert len(picked) == 5
