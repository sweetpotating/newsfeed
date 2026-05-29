"""Mean-reversion sleeve (tactical).

"Buy the dip, but only in an uptrend." For each name:
  * require price ABOVE its long SMA (don't catch falling knives), then
  * scale exposure by how oversold it is on RSI:
        RSI <= rsi_buy_below  -> full target
        RSI >= rsi_sell_above -> no position (overbought; let it go)
        in between            -> linearly interpolated

This is the most active sleeve and is sized smallest in config for that reason.
Weights are normalised so the sleeve never asks for more than 100% of itself.
"""
from __future__ import annotations

import pandas as pd

from .. import indicators
from ..models import Instrument, TargetWeight
from .base import Strategy


class MeanReversionStrategy(Strategy):
    name = "mean_reversion"

    def compute(
        self,
        universe: list[Instrument],
        history: dict[str, pd.Series],
    ) -> list[TargetWeight]:
        rsi_period = int(self.params.get("rsi_period", 14))
        buy_below = float(self.params.get("rsi_buy_below", 30))
        sell_above = float(self.params.get("rsi_sell_above", 70))
        sma_days = int(self.params.get("sma_filter_days", 200))

        raw: list[tuple[Instrument, float]] = []
        for inst in universe:
            s = history.get(inst.key)
            if s is None:
                continue
            s = s.dropna()
            if len(s) <= max(rsi_period, sma_days):
                continue
            sma = indicators.sma(s, sma_days)
            if pd.isna(sma.iloc[-1]) or s.iloc[-1] <= sma.iloc[-1]:
                continue  # only buy dips inside a long-term uptrend
            r = indicators.rsi(s, rsi_period).iloc[-1]
            if pd.isna(r) or r >= sell_above:
                continue
            # Oversold intensity in [0, 1].
            intensity = max(0.0, min(1.0, (sell_above - r) / (sell_above - buy_below)))
            if intensity > 0:
                raw.append((inst, intensity))

        if not raw:
            return []

        total = sum(i for _, i in raw)
        return [
            TargetWeight(inst, intensity / total, reason=f"Mean-reversion (RSI dip)")
            for inst, intensity in raw
        ]
