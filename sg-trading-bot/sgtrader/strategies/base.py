"""Strategy interface.

A strategy is a pure function of (universe, price history, params) -> weights.
Keeping it pure (no broker, no I/O) makes strategies trivial to unit-test and
to run inside the backtester unchanged.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from ..models import Instrument, TargetWeight


class Strategy(ABC):
    #: name used in config (set by subclasses)
    name: str = "base"

    def __init__(self, params: dict | None = None):
        self.params = params or {}

    @abstractmethod
    def compute(
        self,
        universe: list[Instrument],
        history: dict[str, pd.Series],
    ) -> list[TargetWeight]:
        """Return desired weights WITHIN this sleeve (sum <= 1.0).

        `history` maps instrument.key -> daily close Series. A strategy should
        gracefully ignore instruments lacking enough history.
        """

    # ── shared helpers ────────────────────────────────────────────────────
    @staticmethod
    def _equal_weight(instruments: list[Instrument], reason: str) -> list[TargetWeight]:
        if not instruments:
            return []
        w = 1.0 / len(instruments)
        return [TargetWeight(inst, w, reason) for inst in instruments]
