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
import random
from typing import List, Optional

# Header for each reminder — warm, doctor-casual greeting with emojis. {name} is
# the person she's reminding.
GREETINGS: List[str] = [
    "hello {name} 👋 eyedrop time 💧",
    "hi {name} 👩‍⚕️ doctor's orders — drops now 💧",
    "knock knock {name} 🚪 your eyes need their drops 💧",
    "hi {name} 🥰 time for your eyedrops ah 💧",
    "{name} dear 💛 it's drops o'clock 💧",
    "hello {name} 👀 quick, your eyedrops 💧",
    "okay {name} 😌 drops time, chop chop 💧",
    "hi {name} 🌿 let's take care of those eyes — drops 💧",
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

# Rotating eye-care tips live in ``tips.py`` (200+ of them). Selection below
# deals them in a shuffled, no-same-day-repeat order.
from .tips import EYE_CARE_TIPS  # noqa: E402,F401

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


def tip_count() -> int:
    return len(EYE_CARE_TIPS)


def _daily_tip_order(day_key: str) -> List[int]:
    """A stable shuffle of all tip indices for a given day.

    Same day -> same order; different days -> different order. Taking the first
    N entries gives N *distinct* tips, so the day's reminders never repeat one.
    """
    order = list(range(len(EYE_CARE_TIPS)))
    seed = int(hashlib.sha256(("tiporder:" + day_key).encode("utf-8")).hexdigest(), 16)
    random.Random(seed).shuffle(order)
    return order


def tip_for_slot(day_key: str, slot_index: int) -> str:
    """The tip for the Nth reminder of ``day_key`` — no same-day repeats."""
    if not EYE_CARE_TIPS:
        return ""
    order = _daily_tip_order(day_key)
    return EYE_CARE_TIPS[order[slot_index % len(order)]]


def encouragement(seed: str) -> str:
    return _pick(ENCOURAGEMENTS, "cheer:" + seed)


def how_to_block() -> str:
    return "\n".join(f"  {i}. {step}" for i, step in enumerate(HOW_TO_STEPS, 1))


def build_reminder(name: str, seed: str, *, dose_label: str = "",
                   include_howto: bool = False,
                   tip_index: Optional[int] = None) -> str:
    """Compose a full reminder message in Dr Helen's voice.

    ``seed`` makes the wording deterministic for a given day/slot. ``dose_label``
    is an optional "(dose 2 of 4)" style tag. ``include_howto`` adds the
    step-by-step block (handy for the first reminder of the day).

    ``tip_index`` is the reminder's position in the day (0-based). When given,
    the tip is drawn from that day's shuffled order so the day's reminders never
    repeat a tip. Without it, the tip is just seed-based.
    """
    head = greeting(name, seed)
    if dose_label:
        head += f"  <i>{dose_label}</i>"

    if tip_index is not None:
        tip = tip_for_slot(seed.split("|", 1)[0], tip_index)
    else:
        tip = eye_care_tip(seed)

    lines = [head, ""]
    lines.append("💧 put your eyedrops now. don't bluff me ah.")
    if include_howto:
        lines.append("")
        lines.append("<b>quick how-to (don't anyhow):</b>")
        lines.append(how_to_block())
    lines.append("")
    lines.append(no_rub_nudge(seed))
    lines.append("")
    lines.append(tip)
    lines.append("")
    lines.append(encouragement(seed))
    return "\n".join(lines)
