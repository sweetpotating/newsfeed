from datetime import datetime, timezone

from ainews.classifier import classify
from ainews.formatter import MAX_MSG_LEN, format_digest
from ainews.models import Article


def _art(title, **kw):
    a = Article(title=title, link=kw.pop("link", "https://example.com/a"),
                source=kw.pop("source", "Src"), **kw)
    return classify(a)


def test_sections_present_and_ordered():
    arts = [
        _art("Anthropic ships Claude update"),
        _art("Visa launches agentic commerce", source="PYMNTS"),
        _art("AI startup raises funding"),
    ]
    msgs = format_digest(arts, now=datetime(2026, 5, 28, tzinfo=timezone.utc))
    blob = "\n".join(msgs)
    assert "AI Platforms" in blob
    assert "Agentic Payments" in blob
    assert "AI Industry" in blob
    # Platforms section must appear before Agentic, which appears before Industry.
    assert blob.index("AI Platforms") < blob.index("Agentic Payments") < blob.index("AI Industry")


def test_html_escaping():
    a = _art("Tom & Jerry <fight> over AI")
    msg = format_digest([a])[0]
    assert "&amp;" in msg
    assert "&lt;fight&gt;" in msg
    # The raw angle-bracket title must not leak into the HTML.
    assert "<fight>" not in msg


def test_chunking_respects_limit():
    arts = [_art(f"Headline number {i} about AI models " * 5,
                 link=f"https://example.com/{i}") for i in range(200)]
    msgs = format_digest(arts)
    assert len(msgs) > 1
    for m in msgs:
        assert len(m) <= MAX_MSG_LEN


def test_empty_digest_has_header():
    msgs = format_digest([])
    assert len(msgs) == 1
    assert "AI News Digest" in msgs[0]
