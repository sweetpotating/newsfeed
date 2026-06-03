"""The voice of Mimi Helen Bot: reminders, eye-care tips and gentle nudges.

Everything the bot *says* lives here so the wording is easy to tweak without
touching any logic. Messages use a warm, encouraging tone and light HTML
(Telegram's ``parse_mode=HTML``). Selection is deterministic per day+slot so a
given reminder reads consistently within a day but varies across the week.
"""

from __future__ import annotations

import hashlib
from typing import List

# A short header for each reminder, gently rotating so it never feels robotic.
GREETINGS: List[str] = [
    "💧 Eyedrop time, {name}!",
    "👀 Time for your drops, {name} 💧",
    "💧 Gentle reminder, {name} — drops time!",
    "🌿 {name}, let's take care of those eyes 💧",
    "💧 Knock knock — your eyes called, {name}!",
]

# Step-by-step so the routine is done well, not just done.
HOW_TO_STEPS: List[str] = [
    "Wash your hands first 🧼",
    "Tilt your head back &amp; look up 👆",
    "Gently pull down your lower lid to make a pocket",
    "Squeeze <b>one</b> drop in — don't let the tip touch your eye",
    "Close your eyes for ~1 min; press the inner corner softly",
]

# The non-negotiable nudge: don't rub.
NO_RUB_NUDGES: List[str] = [
    "🚫 And remember — <b>no rubbing!</b> If your eyes itch, blink or use a clean cool compress instead.",
    "🙅 Try not to rub your eyes today — rubbing can irritate them and spread germs. A gentle blink helps more.",
    "✋ Itchy eyes? Resist the rub! Close them, take a breath, and let it pass.",
    "🚫 No rubbing, please 💛 Rubbing can scratch the surface of your eye. Cool compress &gt; rubbing.",
    "🙆 If your eyes feel tired, palm them gently with warm hands — but no rubbing!",
]

# Rotating eye-care tips delivered with reminders and via /tips.
EYE_CARE_TIPS: List[str] = [
    "👁️ <b>20-20-20 rule:</b> every 20 min, look at something 20 ft away for 20 sec. Your eyes will thank you.",
    "💦 Stay hydrated — dry eyes love water. Aim for steady sips through the day.",
    "🌙 Good sleep = happier eyes. Try to give them a proper 7-8 hours of rest.",
    "🕶️ Heading out? Sunglasses with UV protection shield your eyes from glare and damage.",
    "💡 Soften harsh screen light and keep your screen an arm's length away.",
    "🐟 Foods rich in omega-3 and vitamin A (fish, carrots, leafy greens) support eye health.",
    "😌 Blink often, especially on screens — we blink ~50% less when staring at devices.",
    "🌬️ Avoid pointing fans or aircon vents straight at your face; moving air dries eyes out.",
    "🧴 Using more than one type of drop? Wait ~5 minutes between them so each one works.",
    "📵 Take a real screen break — a short walk re-moistens and rests your eyes.",
    "🔆 Read in good light; squinting in the dark tires your eyes faster.",
    "🤲 Always wash your hands before touching your eyes or putting in drops.",
]

ENCOURAGEMENTS: List[str] = [
    "You're doing great — small habits, healthy eyes 💛",
    "Future-you says thank you 🌟",
    "One drop at a time. Proud of you! 👏",
    "Consistency is the magic. Keep going! ✨",
    "Your eyes are in good hands 💧",
]


def _pick(options: List[str], seed: str) -> str:
    """Deterministically choose one option from a stable seed string."""
    if not options:
        return ""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return options[int(digest, 16) % len(options)]


def greeting(name: str, seed: str) -> str:
    return _pick(GREETINGS, "greet:" + seed).format(name=name)


def no_rub_nudge(seed: str) -> str:
    return _pick(NO_RUB_NUDGES, "norub:" + seed)


def eye_care_tip(seed: str) -> str:
    return _pick(EYE_CARE_TIPS, "tip:" + seed)


def encouragement(seed: str) -> str:
    return _pick(ENCOURAGEMENTS, "cheer:" + seed)


def how_to_block() -> str:
    return "\n".join(f"  {i}. {step}" for i, step in enumerate(HOW_TO_STEPS, 1))


def build_reminder(name: str, seed: str, *, dose_label: str = "",
                   include_howto: bool = False) -> str:
    """Compose a full reminder message.

    ``seed`` makes the wording deterministic for a given day/slot. ``dose_label``
    is an optional "(dose 2 of 4)" style tag. ``include_howto`` adds the
    step-by-step block (handy for the first reminder of the day).
    """
    head = greeting(name, seed)
    if dose_label:
        head += f"  <i>{dose_label}</i>"

    lines = [head, ""]
    lines.append("💧 Time to put in your eyedrops.")
    if include_howto:
        lines.append("")
        lines.append("<b>Quick how-to:</b>")
        lines.append(how_to_block())
    lines.append("")
    lines.append(no_rub_nudge(seed))
    lines.append("")
    lines.append("<b>Eye-care tip</b> — " + eye_care_tip(seed))
    lines.append("")
    lines.append(encouragement(seed))
    return "\n".join(lines)
