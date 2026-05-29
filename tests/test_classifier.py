from ainews.classifier import classify, detect_platforms, is_agentic
from ainews.models import CAT_AGENTIC, CAT_INDUSTRY, CAT_PLATFORM, Article


def _art(title, summary=""):
    return Article(title=title, link="https://x/y", source="t", summary=summary)


def test_detect_platforms_priority_order():
    plats = detect_platforms("Gemini and Claude both beat GPT-5 today")
    # Claude should come before gemini/chatgpt per priority order.
    assert plats[0] == "claude"
    assert set(plats) == {"claude", "chatgpt", "gemini"}


def test_word_boundary_avoids_false_positive():
    # "o1" must not match inside other words; "grok" should still match alone.
    assert detect_platforms("the o1 model is fast") == ["chatgpt"]
    assert "grok" in detect_platforms("xAI ships Grok update")


def test_platform_classification():
    a = classify(_art("Anthropic releases Claude Opus 4.8"))
    assert a.category == CAT_PLATFORM
    assert a.platforms == ["claude"]


def test_agentic_beats_platform():
    a = classify(_art("OpenAI launches agentic commerce checkout"))
    assert a.category == CAT_AGENTIC
    # Platform tag is retained for the badge.
    assert "chatgpt" in a.platforms


def test_agentic_keywords():
    assert is_agentic("Visa unveils Intelligent Commerce for AI agents")
    assert is_agentic("Stripe agent toolkit and the x402 protocol")
    assert not is_agentic("A normal payments earnings report")


def test_industry_fallback():
    a = classify(_art("Startup raises Series B for data labeling"))
    assert a.category == CAT_INDUSTRY
    assert a.platforms == []
