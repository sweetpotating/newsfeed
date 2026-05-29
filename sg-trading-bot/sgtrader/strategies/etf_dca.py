"""Long-term ETF dollar-cost-averaging sleeve.

The compounding core of the portfolio: hold a fixed, broad set of low-cost
ETFs at equal weight and let new capital + periodic rebalancing keep them on
target. Turnover is intentionally minimal — the risk layer's `min_trade_value`
acts as a no-trade band, so we only trade when a holding has drifted far enough
to be worth the fees.
"""
from __future__ import annotations

import pandas as pd

from ..models import Instrument, TargetWeight
from .base import Strategy


class ETFDCAStrategy(Strategy):
    name = "etf_dca"

    def compute(
        self,
        universe: list[Instrument],
        history: dict[str, pd.Series],
    ) -> list[TargetWeight]:
        # Equal-weight every ETF we actually have a price for.
        priced = [inst for inst in universe if _has_price(history, inst)]
        return self._equal_weight(priced, reason="ETF DCA equal-weight core")


def _has_price(history: dict[str, pd.Series], inst: Instrument) -> bool:
    s = history.get(inst.key)
    return s is not None and len(s.dropna()) > 0
