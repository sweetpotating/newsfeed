"""The voice of Mimi Helen Bot — written to sound like Dr Helen herself.

Dr Helen Mi is an eye surgeon, and a dear friend. Her texting voice (lovingly
studied from real chats) is: all lowercase, short clipped lines, full-stops for
emphasis, heavy Singlish (lah/leh/lor/ma/hor/sian/jialat/severe/kelian), fierce
tough-love on the surface — "stop.", "don't bluff me", "i'm watching 👀" — and
genuinely caring underneath ("rest well", "drive safe", "eat properly", "xx").

So the reminders nag you the way she would: blunt, funny, a little scary, but
only because she actually wants your eyes (and you) to be ok.

Everything the bot *says* lives here so the wording is easy to tweak. Messages
use light HTML (Telegram's ``parse_mode=HTML``). Selection is deterministic per
day+slot so a reminder reads consistently within a day but varies across days.
"""

from __future__ import annotations

import hashlib
from typing import List

# Header for each reminder — Helen nagging you about your drops. {name} is the
# person she's reminding.
GREETINGS: List[str] = [
    "{name}. eyedrop time. just.",
    "oi {name}, drops. now 💧",
    "{name} ah, you put your eyedrops liao not 💧",
    "{name}, drops. don't make me come find you 💧",
    "eyedrop time {name}. pls don't bluff me 💧",
    "{name}, it's drops o'clock. chop chop 💧",
    "{name}. eyes. drops. now. full stop.",
]

# Step-by-step. Matter-of-fact, the way a doctor who's done it 10,000 times
# would rattle it off.
HOW_TO_STEPS: List[str] = [
    "wash your hands first. don't anyhow 🧼",
    "head back, look up 👆",
    "pull your lower lid down, make a small pocket",
    "<b>one</b> drop only. don't let the bottle touch your eye ah",
    "close your eyes 1 min, press the inner corner. then you done",
]

# The non-negotiable: no rubbing. This is the eye doctor talking.
NO_RUB_NUDGES: List[str] = [
    "and NO rubbing your eyes. i'm serious. 🚫",
    "stop rubbing your eyes leh. itchy then blink or cold compress. don't rub.",
    "no rubbing ah. you rub, i scold you 😤",
    "eyes itchy? don't rub lah. cool compress &gt; rubbing. trust me, i'm the eye doctor.",
    "rubbing your eyes is a no. full stop. 🚫",
    "don't rub your eyes hor. you'll regret. just blink blink 🙅",
]

# Rotating eye-care tips, delivered Helen-style.
EYE_CARE_TIPS: List[str] = [
    "20-20-20 ah: every 20 min, look 20 feet away for 20 sec. your eyes not iron made 👁️",
    "drink water lah. dry eyes very 辛苦 one 💦",
    "sleep properly. 7-8 hours. your eyes also need rest 🌙",
    "going out? sunglasses. UV is real one 🕶️",
    "screen too bright then dim it. arm's length away. don't paste your face on the screen 💡",
    "blink more when you're on your phone. you all blink until forget how to blink 😮‍💨",
    "don't aim the fan or aircon straight at your face. dries the eyes out 🌬️",
    "two types of drops? wait 5 min in between. don't rush.",
    "take a screen break. go walk a bit. your eyes will thank you 📵",
    "eat your greens and fish. good for the eyes. i'm not joking 🐟",
    "wash your hands before touching your eyes. always.",
    "read in proper light. squinting in the dark very jialat for the eyes 🔆",
]

# Tough-love sign-offs. Fierce but she's proud of you really.
ENCOURAGEMENTS: List[str] = [
    "ok good. small thing but you did it 👌🏼",
    "see, not hard right. proud of you 🤍",
    "consistent ah. don't 半途而废 💪🏻",
    "good. your eyes happy liao 🧡",
    "ok next round don't forget. i'm watching 👀",
    "done liao? good. now go rest 🤍",
    "i'm not always right but i'm hardly wrong — and i say: do your drops. 😤",
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
    """Compose a full reminder message in Dr Helen's voice.

    ``seed`` makes the wording deterministic for a given day/slot. ``dose_label``
    is an optional "(dose 2 of 4)" style tag. ``include_howto`` adds the
    step-by-step block (handy for the first reminder of the day).
    """
    head = greeting(name, seed)
    if dose_label:
        head += f"  <i>{dose_label}</i>"

    lines = [head, ""]
    lines.append("💧 put your eyedrops now. don't bluff me ah.")
    if include_howto:
        lines.append("")
        lines.append("<b>quick how-to (don't anyhow):</b>")
        lines.append(how_to_block())
    lines.append("")
    lines.append(no_rub_nudge(seed))
    lines.append("")
    lines.append(eye_care_tip(seed))
    lines.append("")
    lines.append(encouragement(seed))
    return "\n".join(lines)
