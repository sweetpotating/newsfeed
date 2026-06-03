"""Build a forwardable eyedrop-compliance report.

`/report` produces a single, self-contained message the user can forward to her
eye doctor (Dr Helen) to show adherence. It's deliberately neutral/clinical
(not the bot's joking voice) since a real clinician reads it, and it's honest
about its source: the figures are what was logged in the bot.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def _verdict(pct: float) -> str:
    if pct >= 90:
        return "Excellent adherence ✅"
    if pct >= 70:
        return "Good adherence, a few missed doses 👍"
    if pct >= 40:
        return "Partial adherence — several missed doses ⚠️"
    return "Low adherence — many missed doses ❗"


def build_report(cfg, tracker, now: datetime, days: int = 7) -> str:
    """Return an HTML compliance report over the last ``days`` days."""
    days = max(1, min(days, 60))
    goal = max(1, cfg.daily_goal)
    end = now.date()
    start = end - timedelta(days=days - 1)

    rows, total_logged, days_met = [], 0, 0
    for i in range(days):
        d = start + timedelta(days=i)
        cnt = tracker.doses_on(d)
        total_logged += cnt
        if cnt >= goal:
            mark, days_met = "✅", days_met + 1
        elif cnt > 0:
            mark = "⚠️"
        else:
            mark = "❌"
        rows.append(f"{mark} {d.strftime('%a %d %b')} — {cnt}/{goal}")

    expected = goal * days
    drop_pct = round(100 * min(total_logged, expected) / expected) if expected else 0
    day_pct = round(100 * days_met / days)
    streak = tracker.streak(end)
    period = f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"

    lines = [
        "<b>👁️ Eyedrop Compliance Report</b>",
        f"<b>Patient:</b> {cfg.friend_name}",
        f"<b>Period:</b> {period} ({days} day{'s' if days != 1 else ''})",
        f"<b>Prescribed:</b> {goal}×/day — {', '.join(cfg.times)} ({cfg.tz})",
    ]
    if cfg.eyedrops:
        lines.append(f"<b>Drops:</b> {cfg.eyedrops}")
    lines += [
        "",
        "<b>Daily log</b>",
        *rows,
        "",
        "<b>Summary</b>",
        f"• Days on target: {days_met}/{days} ({day_pct}%)",
        f"• Doses logged: {total_logged}/{expected} ({drop_pct}%)",
        f"• Current streak: {streak} day{'s' if streak != 1 else ''}",
        "",
        f"<b>Assessment:</b> {_verdict(day_pct)}",
        "",
        f"<i>Self-reported via Mimi Helen Bot. Counts reflect doses logged in the "
        f"bot. Generated {now.strftime('%d %b %Y, %H:%M')} ({cfg.tz}).</i>",
    ]
    return "\n".join(lines)
