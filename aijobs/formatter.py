"""Render jobs into Telegram-ready HTML messages (one post per role)."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import List

from .models import Job

# Stay comfortably under Telegram's 4096 hard limit.
MAX_MSG_LEN = 3800

ROLE_BADGES = {
    "research": "🔬 Research",
    "ml": "🧠 ML/AI",
    "data": "📊 Data",
    "ai-product": "🛠️ AI Product",
    "ai-safety": "🛡️ Safety",
    "infra": "⚙️ AI Infra",
}


def _time_ago(dt: datetime | None) -> str:
    if dt is None:
        return ""
    secs = int((datetime.now(timezone.utc) - dt).total_seconds())
    if secs < 0:
        return "just now"
    if secs < 3600:
        return f"{max(1, secs // 60)}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


def _meta(job: Job) -> str:
    parts: List[str] = [escape(job.company)]
    if job.location:
        parts.append(escape(job.location))
    badges = [ROLE_BADGES[t] for t in job.role_tags if t in ROLE_BADGES]
    if badges:
        parts.append(" · ".join(badges[:3]))
    ago = _time_ago(job.posted)
    if ago:
        parts.append(ago)
    return " · ".join(parts)


def render_post(job: Job, max_len: int = MAX_MSG_LEN) -> str:
    """Render a single job as one rich HTML post.

    Layout:
        ⭐ Priority AI Lab        (only for the marquee labs)
        <b>Title (linked)</b>
        Company · Location · role badges · time

        <blurb, if any>
        Apply →
    """
    title = escape(job.title)
    link = escape(job.url, quote=True)

    lines: List[str] = []
    if job.is_priority_lab:
        lines.append("⭐ <b>Priority AI Lab</b>")
    lines.append(f'<b><a href="{link}">{title}</a></b>')
    lines.append("<i>" + _meta(job) + "</i>")

    if job.summary:
        lines.append("")
        lines.append(escape(job.summary))

    lines.append("")
    lines.append(f'<a href="{link}">Apply →</a>')

    text = "\n".join(lines)
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def render_header(n: int, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%a %d %b %Y, %H:%M UTC")
    return (
        f"💼 <b>AI Jobs in Singapore</b> · {stamp}\n"
        f"<i>{n} new opening{'s' if n != 1 else ''}</i>"
    )
