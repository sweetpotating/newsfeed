"""Answer free-text questions from the user — in Dr Helen's voice.

Two layers:

1. **Deterministic answers** (no network, always work): "when's my next
   reminder", the full schedule, today's count, streak, why-no-rubbing,
   how-to-use-drops, and info about the specific drops she's on (configurable
   via ``MIMIHELEN_EYEDROPS``).
2. **Optional LLM fallback** for anything open-ended. Reuses ``ANTHROPIC_API_KEY``
   if present; otherwise the bot just points her at what it *can* answer.

Medical safety: answers are general eye-care info only. We never diagnose, never
change a prescription, and always defer to her real eye doctor / pharmacist. The
LLM prompt is locked to the same rules.

Q&A only runs in ``serve`` mode (the long-polling bot can receive messages). The
scheduled ``remind`` cron is push-only and never calls this.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional

log = logging.getLogger("mimihelen.qa")

DISCLAIMER = (
    "\n\n<i>(i'm just the reminder bot ah, not the real dr helen. for anything "
    "specific about your eyes or your drops, listen to your own eye doctor / "
    "pharmacist.)</i>"
)


def _minutes(hhmm: str) -> int:
    hh, mm = hhmm.split(":")
    return int(hh) * 60 + int(mm)


def _fmt_delta(mins: int) -> str:
    if mins <= 0:
        return "now"
    h, m = divmod(mins, 60)
    if h and m:
        return f"in {h}h {m}min"
    if h:
        return f"in {h}h"
    return f"in {m}min"


def next_reminder(times: List[str], now: datetime) -> Optional[str]:
    """Human-readable description of the next scheduled reminder, or None."""
    if not times:
        return None
    ordered = sorted(times, key=_minutes)
    now_min = now.hour * 60 + now.minute
    for t in ordered:
        if _minutes(t) > now_min:
            delta = _minutes(t) - now_min
            return f"today at <b>{t}</b> ({_fmt_delta(delta)})"
    # Nothing left today -> first slot tomorrow.
    first = ordered[0]
    delta = (24 * 60 - now_min) + _minutes(first)
    return f"tomorrow at <b>{first}</b> ({_fmt_delta(delta)})"


# ---- intent helpers ----------------------------------------------------
def _has(t: str, *words: str) -> bool:
    return any(w in t for w in words)


def _drops_word(t: str) -> bool:
    return _has(t, "eyedrop", "eye drop", "eye-drop", "drops", "drop")


def eyedrop_info(cfg) -> str:
    """What the drops are / how they help. Uses her configured Rx if provided."""
    if cfg.eyedrops:
        return (
            f"💧 your drops: {cfg.eyedrops}\n\n"
            "use them as prescribed, don't skip, don't anyhow stop halfway just "
            "because your eye feels better. if it stings a lot, gets very red, "
            "or vision drops — that's not normal, go see your eye doctor."
            + DISCLAIMER
        )
    # No specific Rx configured — give a useful general primer.
    return (
        "i don't know your exact prescription (set it and i'll remember), but in "
        "general eyedrops are usually one of these 👇\n\n"
        "• <b>lubricating / artificial tears</b> — for dry, tired eyes. keeps the "
        "surface moist & comfortable.\n"
        "• <b>anti-inflammatory / steroid</b> — calms swelling/inflammation after "
        "surgery or a flare. must use exactly as told.\n"
        "• <b>antibiotic</b> — for an infection. finish the full course.\n"
        "• <b>pressure-lowering (glaucoma)</b> — keeps eye pressure down. same "
        "time every day matters.\n"
        "• <b>anti-allergy</b> — for itchy, watery allergic eyes.\n\n"
        "check the bottle label, and follow what your eye doctor prescribed."
        + DISCLAIMER
    )


def how_to_use() -> str:
    from . import content  # local import to avoid any cycle
    return (
        "how to put your drops properly 👇\n\n"
        + content.how_to_block()
        + "\n\nand don't let the bottle tip touch your eye/lashes — that's how it "
        "gets contaminated." + DISCLAIMER
    )


def why_no_rub() -> str:
    return (
        "no rubbing ah, i'm serious 🚫\n\n"
        "rubbing feels good for 2 sec but it: irritates the surface, can scratch "
        "the cornea, spreads germs from your hands, and makes any swelling/allergy "
        "worse. itchy → blink, or a clean cool compress. not rub." + DISCLAIMER
    )


def _today_text(cfg, tracker, now: datetime) -> str:
    n = tracker.doses_on(now.date())
    goal = cfg.daily_goal
    if n >= goal:
        return f"you've done {n}/{goal} today. goal hit 👌🏼 good."
    return f"you've done {n}/{goal} today. {goal - n} more to go. don't 半途而废 ah 💪🏻"


def _schedule_text(cfg) -> str:
    return (
        f"🕒 your reminders ({cfg.tz}):\n{', '.join(cfg.times)}\n\n"
        f"🎯 {cfg.daily_goal} drops a day."
    )


def _streak_text(cfg, tracker, now: datetime) -> str:
    s = tracker.streak(now.date())
    if s <= 0:
        return "no streak yet leh. do today's drops and start one 💪🏻"
    return f"🔥 {s} day{'s' if s != 1 else ''} in a row you hit your goal. don't break it ah."


# ---- main entry --------------------------------------------------------
def answer(question: str, cfg, tracker, now: datetime) -> str:
    """Best-effort answer to a free-text question, in Dr Helen's voice."""
    t = question.lower().strip()

    # next reminder — check before the general "schedule" intent.
    if _has(t, "next") and (_has(t, "remind", "dose", "drop") or "when" in t):
        nxt = next_reminder(cfg.times, now)
        if nxt:
            return f"💧 your next drops: {nxt}. i'll buzz you, don't worry."
        return "no reminder times set leh."

    # full schedule / all times
    if _has(t, "schedule") or (_has(t, "what time", "when") and _has(t, "remind", "reminders")) \
            or _has(t, "all the time", "all my time", "my reminders", "my timing"):
        return _schedule_text(cfg)

    # today's progress
    if _has(t, "progress") or (_has(t, "how many") and _drops_word(t)) \
            or t in ("today", "how many today", "how many left"):
        return _today_text(cfg, tracker, now)

    if "streak" in t:
        return _streak_text(cfg, tracker, now)

    # how to use the drops (check before generic "what drops")
    if _has(t, "how") and _has(t, "use", "put", "apply", "instil", "instill", "do i") \
            and _drops_word(t):
        return how_to_use()

    # no-rubbing
    if "rub" in t:
        return why_no_rub()

    # what are the drops / how do they help / what for
    if (_has(t, "what", "which", "why", "tell me about") and _drops_word(t)) \
            or (_has(t, "how") and _has(t, "help", "work") and _drops_word(t)) \
            or _has(t, "what is this for", "what for"):
        return eyedrop_info(cfg)

    # side effects / discomfort
    if _has(t, "side effect", "sting", "burn", "red", "blur", "pain") and _drops_word(t):
        return (
            "a little sting for a few seconds can be normal. but if it really "
            "stings, your eye goes very red, or your vision drops — stop and see "
            "your eye doctor. don't tahan." + DISCLAIMER
        )

    # Fall back to the LLM if configured, else a helpful menu.
    llm = _llm_answer(cfg, question)
    if llm:
        return llm
    return (
        "i didn't quite get that 🙈 but i can tell you:\n"
        "• when's your next reminder\n"
        "• your full schedule\n"
        "• how many drops you've done today / your streak\n"
        "• what your eyedrops are &amp; how to use them\n"
        "• why you shouldn't rub your eyes\n\n"
        "just ask lah. or /help."
    )


def _llm_answer(cfg, question: str) -> Optional[str]:
    """Open-ended answer via Claude, in persona, with safety guardrails."""
    if not cfg.anthropic_api_key:
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic not installed; skipping LLM answer.")
        return None

    rx = cfg.eyedrops or "(not specified — don't assume which drops she's on)"
    system = (
        "You are 'Mimi Helen Bot', texting as Dr Helen — a warm but blunt "
        "Singaporean eye doctor. Voice: all lowercase, short, Singlish "
        "(lah/leh/lor/ma/sian/jialat), fierce-but-caring, occasional 💧🤍. "
        "You help a friend with her eyedrop routine and eye care.\n\n"
        "STRICT RULES:\n"
        "- General eye-care info only. NEVER diagnose, NEVER prescribe, NEVER "
        "tell her to change/stop a prescription.\n"
        "- For anything specific to her eyes or her drops, defer to her own eye "
        "doctor / pharmacist.\n"
        "- Red flags (sudden vision loss, severe pain, a lot of redness, "
        "flashes/floaters, injury) → tell her to see a doctor promptly.\n"
        "- Keep it to a few short sentences. No markdown headers, light HTML "
        "(<b>, <i>) is ok.\n"
        f"- Her prescribed drops: {rx}.\n"
        f"- Her reminder times ({cfg.tz}): {', '.join(cfg.times)}."
    )
    try:
        client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
        resp = client.messages.create(
            model=cfg.qa_model,
            max_tokens=350,
            system=system,
            messages=[{"role": "user", "content": question}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        text = "".join(parts).strip()
        return (text + DISCLAIMER) if text else None
    except Exception as exc:  # never let a Q&A failure crash the bot
        log.warning("LLM answer failed: %s", exc)
        return None
