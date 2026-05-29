"""Render classified articles into Telegram-ready HTML messages.

Telegram caps a message at 4096 chars, so the digest is emitted as a list of
message strings, each under a safe limit. Section headers repeat with a
"(cont.)" marker when a section spills across messages.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Dict, List

from .classifier import PLATFORM_LABELS, PLATFORM_ORDER
from .models import CAT_AGENTIC, CAT_INDUSTRY, CAT_PLATFORM, Article

# Stay comfortably under Telegram's 4096 hard limit.
MAX_MSG_LEN = 3800
# Telegram caps a photo caption at 1024 chars. Keep a safety margin.
MAX_CAPTION_LEN = 1000

SECTION_TITLES = {
    CAT_PLATFORM: "🤖 AI Platforms",
    CAT_AGENTIC: "💳 Agentic Payments & Commerce",
    CAT_INDUSTRY: "🌐 AI Industry",
}
# Display order of the top-level sections.
SECTION_ORDER = [CAT_PLATFORM, CAT_AGENTIC, CAT_INDUSTRY]

CATEGORY_TAG = {
    CAT_PLATFORM: "🤖 AI Platform",
    CAT_AGENTIC: "💳 Agentic Commerce",
    CAT_INDUSTRY: "🌐 AI Industry",
}

REGION_BADGE = {"asia": "🌏 Asia", "official": "📣 Official", "global": "🌍 Global"}


def _time_ago(dt: datetime | None) -> str:
    if dt is None:
        return ""
    now = datetime.now(timezone.utc)
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 0:
        return "just now"
    if secs < 3600:
        return f"{max(1, secs // 60)}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


def _platform_sort_index(article: Article) -> int:
    if not article.platforms:
        return len(PLATFORM_ORDER)
    return PLATFORM_ORDER.index(article.platforms[0])


def _render_entry(article: Article) -> str:
    title = escape(article.title)
    link = escape(article.link, quote=True)

    badges: List[str] = []
    for key in article.platforms:
        label = PLATFORM_LABELS.get(key)
        if label:
            badges.append(label)
    meta = [escape(article.source)]
    if badges:
        meta.append(" · ".join(badges))
    region = REGION_BADGE.get(article.region)
    if region and article.region != "global":
        meta.append(region)
    ago = _time_ago(article.published)
    if ago:
        meta.append(ago)

    line1 = f'• <a href="{link}">{title}</a>'
    # Note: source/region/ago are already escaped above as needed; badges are
    # static safe strings. Join with a plain separator inside italics.
    meta_line = "   <i>" + " · ".join(meta) + "</i>"
    return f"{line1}\n{meta_line}\n"


def _meta_badges(article: Article) -> List[str]:
    """Source · platform badges · region · time-ago — each piece pre-escaped."""
    meta = [escape(article.source)]
    badges = [PLATFORM_LABELS[k] for k in article.platforms if k in PLATFORM_LABELS]
    if badges:
        meta.append(" · ".join(badges))
    region = REGION_BADGE.get(article.region)
    if region and article.region != "global":
        meta.append(region)
    ago = _time_ago(article.published)
    if ago:
        meta.append(ago)
    return meta


def render_post(article: Article, max_len: int = MAX_MSG_LEN) -> str:
    """Render a single article as one rich HTML post.

    Layout:
        <category tag>
        <b>Title (linked)</b>
        source · platform · region · time

        • takeaway 1
        • takeaway 2
        • takeaway 3
        Read more →
    """
    title = escape(article.title)
    link = escape(article.link, quote=True)
    cat_tag = CATEGORY_TAG.get(article.category, "")

    lines: List[str] = []
    if cat_tag:
        lines.append(cat_tag)
    lines.append(f'<b><a href="{link}">{title}</a></b>')
    lines.append("<i>" + " · ".join(_meta_badges(article)) + "</i>")

    if article.takeaways:
        lines.append("")
        for t in article.takeaways[:3]:
            lines.append(f"• {escape(t)}")
    elif article.summary:
        # No AI takeaways — fall back to the feed blurb.
        lines.append("")
        lines.append(escape(article.summary))

    lines.append("")
    lines.append(f'<a href="{link}">Read more →</a>')

    text = "\n".join(lines)
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def _group(articles: List[Article]) -> Dict[str, List[Article]]:
    buckets: Dict[str, List[Article]] = {c: [] for c in SECTION_ORDER}
    for a in articles:
        buckets.setdefault(a.category, []).append(a)
    # Sort platform section by platform priority then recency; others by recency.
    buckets[CAT_PLATFORM].sort(
        key=lambda a: (_platform_sort_index(a), a.sort_key), reverse=False
    )
    buckets[CAT_PLATFORM].sort(key=lambda a: _platform_sort_index(a))
    for cat in (CAT_AGENTIC, CAT_INDUSTRY):
        buckets[cat].sort(key=lambda a: a.sort_key, reverse=True)
    return buckets


def format_digest(articles: List[Article],
                  now: datetime | None = None) -> List[str]:
    """Return a list of HTML message strings ready for Telegram."""
    now = now or datetime.now(timezone.utc)
    buckets = _group(articles)
    total = sum(len(v) for v in buckets.values())

    header = (
        f"🗞️ <b>AI News Digest</b> · {now.strftime('%a %d %b %Y, %H:%M UTC')}\n"
        f"<i>{total} new item{'s' if total != 1 else ''}</i>\n"
    )

    messages: List[str] = []
    buf = header

    for cat in SECTION_ORDER:
        items = buckets.get(cat) or []
        if not items:
            continue
        section_head = f"\n<b>{SECTION_TITLES[cat]}</b>\n"
        if len(buf) + len(section_head) > MAX_MSG_LEN:
            messages.append(buf.rstrip())
            buf = ""
        buf += section_head
        for art in items:
            entry = _render_entry(art)
            if len(buf) + len(entry) > MAX_MSG_LEN:
                messages.append(buf.rstrip())
                buf = f"\n<b>{SECTION_TITLES[cat]}</b> <i>(cont.)</i>\n"
            buf += entry

    if buf.strip():
        messages.append(buf.rstrip())
    return messages
