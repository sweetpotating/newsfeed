"""Mimi Helen Bot — a gentle eyedrop & eye-care reminder bot for Telegram.

Built for one purpose: help a friend remember to use her eyedrops 3-5 times a
day, take care of her eyes, and *not* rub them. It has two run modes:

* ``remind`` — push the reminder due for the current time slot. Stateless and
  perfect for a free GitHub Actions cron (no server needed).
* ``serve`` — a long-polling interactive bot (commands + inline buttons) that
  lets her log doses, see her daily progress, keep a streak and pull eye-care
  tips on demand. Run this anywhere you can keep a small process alive.

The two modes share the same reminder/tip content and the same on-disk tracker
so progress is consistent however you deploy it.
"""

__version__ = "1.0.0"
