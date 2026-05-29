"""Dividend / income sleeve.

Holds a basket of income-oriented names at equal weight as a lower-volatility
ballast. This is a deliberately simple, robust allocation: equal-weighting a
curated quality basket avoids over-fitting and keeps turnover low. (Yield-based
tilting can be added once a dividend-data feed is wired in.)
"""
from __future__ import annotations

import pandas as pd

from ..models import Instrument, TargetWeight
from .base import Strategy


class DividendStrategy(Strategy):
    name = "dividend"

    def compute(
        self,
        universe: list[Instrument],
        history: dict[str, pd.Series],
    ) -> list[TargetWeight]:
        priced = [
            inst for inst in universe
            if (s := history.get(inst.key)) is not None and len(s.dropna()) > 0
        ]
        return self._equal_weight(priced, reason="Dividend basket equal-weight")
