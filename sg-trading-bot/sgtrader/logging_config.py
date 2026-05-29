"""Centralised logging setup. One call configures readable, timestamped logs."""
from __future__ import annotations

import logging
import os
import sys


def setup_logging(level: str | None = None) -> logging.Logger:
    level = (level or os.getenv("SGTRADER_LOG_LEVEL", "INFO")).upper()
    root = logging.getLogger("sgtrader")
    if root.handlers:  # already configured
        return root
    root.setLevel(level)
    # Logs go to stderr so stdout stays clean for machine-readable output
    # (e.g. the JSON report from `rebalance`).
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.propagate = False
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"sgtrader.{name}")
