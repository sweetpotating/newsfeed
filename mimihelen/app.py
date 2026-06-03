"""Mimi Helen Bot entry point.

    python -m mimihelen remind            # send the reminder due now (cron)
    python -m mimihelen remind --dry-run  # print it, send nothing
    python -m mimihelen remind --force    # send even if no slot is due now
    python -m mimihelen serve             # interactive long-polling bot

``remind`` is stateless-friendly and meant for a scheduled GitHub Action: it
figures out which dose slot is due, composes a warm reminder (with the no-rub
nudge + an eye-care tip), sends it with action buttons, and records that a
reminder went out. ``serve`` runs the interactive bot.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import List, Optional

from . import content
from .bot import serve
from .config import Config
from .schedule import current_slot, nearest_slot, now_in_tz, Slot
from .telegram import TelegramClient, reminder_keyboard
from .tracker import DoseTracker

log = logging.getLogger("mimihelen")


def _compose(cfg: Config, slot: Optional[Slot], seed_extra: str) -> str:
    now = now_in_tz(cfg.tz)
    seed = now.strftime("%Y-%m-%d") + "|" + seed_extra
    dose_label = slot.dose_label if slot else ""
    include_howto = bool(slot and slot.is_first)
    return content.build_reminder(
        cfg.friend_name, seed,
        dose_label=dose_label, include_howto=include_howto,
    )


def run_remind(cfg: Config, args: argparse.Namespace) -> int:
    now = now_in_tz(cfg.tz)
    slot = current_slot(cfg.times, now, cfg.slot_tolerance_min)

    if slot is None and not (args.force or args.dry_run):
        log.info(
            "No reminder slot within %d min of %s (%s). Nothing to send.",
            cfg.slot_tolerance_min, now.strftime("%H:%M"), cfg.tz,
        )
        return 0

    # For force/dry-run with no exact slot, tag with the nearest one anyway.
    effective_slot = slot or nearest_slot(cfg.times, now)
    seed_extra = effective_slot.time_str if effective_slot else "adhoc"
    text = _compose(cfg, effective_slot, seed_extra)

    if args.dry_run:
        print(text)
        return 0

    cfg.require_telegram()
    client = TelegramClient(cfg.bot_token, cfg.chat_id, timeout=cfg.timeout)
    client.send_message(text, reply_markup=reminder_keyboard())
    log.info("Sent reminder (%s).", seed_extra)

    if not args.no_state:
        tracker = DoseTracker(cfg.state_file, daily_goal=cfg.daily_goal)
        tracker.note_reminder(now)
        tracker.prune(now.date())
        tracker.save()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mimihelen",
        description="Mimi Helen Bot — eyedrop & eye-care reminders on Telegram.",
    )
    # -v/--verbose is accepted both before and after the subcommand so that
    # `mimihelen -v remind` and `mimihelen remind -v` both work.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="store_true")

    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command")

    p_remind = sub.add_parser("remind", parents=[common],
                              help="Send the reminder due now (cron).")
    p_remind.add_argument("--dry-run", action="store_true",
                          help="Print the reminder; send nothing, save no state.")
    p_remind.add_argument("--force", action="store_true",
                          help="Send even if no scheduled slot is due right now.")
    p_remind.add_argument("--no-state", action="store_true",
                          help="Do not read or write the tracker state file.")

    sub.add_parser("serve", parents=[common],
                   help="Run the interactive long-polling bot.")
    return parser


def run(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = Config.from_env()

    if args.command == "serve":
        return serve(cfg)
    if args.command == "remind":
        return run_remind(cfg, args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(run())
