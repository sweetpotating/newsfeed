"""Semantic dedup: parsing, graceful fallback, integration, and rendering."""

from datetime import datetime, timedelta, timezone

from ainews import digest
from ainews.classifier import classify
from ainews.cluster import _parse_decisions, cluster_duplicates
from ainews.config import Config
from ainews.formatter import render_post
from ainews.models import Article
from ainews.state import SeenStore


def test_parse_decisions_maps_rep_and_stale():
    data = {"items": [
        {"id": 0, "duplicate_of_recent": False, "same_as_candidate_id": None},
        {"id": 1, "duplicate_of_recent": False, "same_as_candidate_id": 0},
        {"id": 2, "duplicate_of_recent": True, "same_as_candidate_id": None},
        # Forward/equal references are illegal and must be ignored.
        {"id": 3, "duplicate_of_recent": False, "same_as_candidate_id": 5},
        {"id": 4, "duplicate_of_recent": False, "same_as_candidate_id": 4},
    ]}
    rep_of, stale = _parse_decisions(data, n=5)
    assert rep_of == {1: 0}
    assert stale == {2}


def test_parse_decisions_tolerates_garbage():
    assert _parse_decisions({}, 3) == ({}, set())
    assert _parse_decisions({"items": [{"nope": 1}]}, 3) == ({}, set())


def test_cluster_without_key_is_noop():
    arts = [Article(title="a", link="x", source="s"),
            Article(title="b", link="y", source="t")]
    assert cluster_duplicates(arts, [], api_key="", model="m") == ({}, set())


def _art(title, link, hours_ago=1, source="Src"):
    return Article(title=title, link=link, source=source, uid=link,
                   published=datetime.now(timezone.utc)
                   - timedelta(hours=hours_ago))


# The real Anthropic-ban cluster that leaked into the channel on 2026-06-13.
BAN_VARIANTS = [
    ("US government forces Anthropic to disable Claude Fable 5 and Mythos 5 "
     "for all customers worldwide", "TechCrunch AI"),
    ("Anthropic cuts off Fable 5 and Mythos 5 access following government "
     "order", "The Verge"),
    ("Amazon security research reportedly led to the White House's Anthropic "
     "Fable ban", "PYMNTS"),
    ("Anthropic shuts down Fable, Mythos models following Trump admin "
     "directive", "Ars Technica"),
]


def test_select_uses_semantic_dedup_and_records_also_in(tmp_path, monkeypatch):
    store = SeenStore(str(tmp_path / "seen.json"))
    feed = [_art(t, f"https://x/{i}", source=src)
            for i, (t, src) in enumerate(BAN_VARIANTS)]
    feed.append(_art("Meta signs first AI data center deal in India",
                     "https://x/meta", source="TechCrunch AI"))
    monkeypatch.setattr(digest, "fetch_all", lambda *a, **k: list(feed))

    # Fake the LLM: fold every remaining ban headline into the first ban one
    # in the (lexically-reduced, ranked) pool. Robust to ranking order.
    def _is_ban(a):
        return "Anthropic" in a.title or "Fable" in a.title

    def fake_cluster(arts, recent, key, model, timeout=60):
        ban_idx = [i for i, a in enumerate(arts) if _is_ban(a)]
        if not ban_idx:
            return {}, set()
        first = ban_idx[0]
        return {i: first for i in ban_idx[1:]}, set()
    monkeypatch.setattr(digest, "cluster_duplicates", fake_cluster)

    cfg = Config(max_items=5, anthropic_api_key="k", summarize=True)
    picked = digest.select_articles(cfg, store, lookback_hours=24)

    # The whole ban cluster collapses to a single story, plus the Meta story.
    assert len(picked) == 2
    ban = next(a for a in picked if _is_ban(a))
    # Every ban outlet is accounted for: the survivor's own source plus the
    # other three credited via "also covered by".
    all_sources = {src for _, src in BAN_VARIANTS}
    assert {ban.source} | set(ban.also_in) == all_sources
    assert len(set(ban.also_in)) == 3


def test_select_semantic_marks_stale_against_recent(tmp_path, monkeypatch):
    store = SeenStore(str(tmp_path / "seen.json"))
    feed = [_art("Anthropic shuts down Fable following government directive",
                 "https://x/1", source="Ars Technica"),
            _art("OpenAI launches new Codex features", "https://x/2",
                 source="OpenAI News")]
    monkeypatch.setattr(digest, "fetch_all", lambda *a, **k: list(feed))

    def fake_cluster(arts, recent, key, model, timeout=60):
        # Candidate 0 duplicates something already shared in the last 24h.
        return {}, {0}
    monkeypatch.setattr(digest, "cluster_duplicates", fake_cluster)

    cfg = Config(max_items=5, anthropic_api_key="k", summarize=True)
    titles = [a.title for a in digest.select_articles(cfg, store, 24)]
    assert titles == ["OpenAI launches new Codex features"]


def test_render_post_shows_also_covered_by():
    a = classify(Article(title="Big AI story", link="https://x/a",
                         source="TechCrunch AI", summary="blurb"))
    a.also_in = ["The Verge", "PYMNTS", "the verge", "TechCrunch AI"]
    post = render_post(a)
    assert "Also covered by:" in post
    assert "The Verge" in post and "PYMNTS" in post
    # De-duplicated and primary source excluded.
    assert post.count("The Verge") == 1
    assert "Also covered by: TechCrunch AI" not in post
